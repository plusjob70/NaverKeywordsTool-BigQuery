#! python
import os
import gspread
import pandas as pd
import common.queries as queries
from time import sleep
from common.constant import IS_DANGEROUS_TIME
from common.uinfo import *
from keywordanal import Keywordanal
from service.gmailservice import GmailService
from google.cloud import bigquery
from googleapiclient.discovery import build
from google.cloud.exceptions import NotFound
from oauth2client.service_account import ServiceAccountCredentials

if __name__ == '__main__':
    msg    = []
    text   = ''
    status = 'succeeded'
    gmail  = GmailService()

    # check dangerous time
    if (IS_DANGEROUS_TIME):
        text = 'Deny access to the server. It is a dangerous time.'
        print(text)
        gmail.send_message(gmail.create_message(text, 'failed'))
        exit()

    # set google application credentials for Bigquery
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = KEYPATH

    # authorize gsheet and gdrive
    scopes = ['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
    creds  = ServiceAccountCredentials.from_json_keyfile_name(KEYPATH, scopes)
    gdrive = build('drive', 'v3', credentials=creds)
    gspd   = gspread.authorize(credentials=creds)

    # get client file info (id, name)
    nst_data_id      = gdrive.files().list(q=f'name=\'{GDRIVE_DIR_NAME}\'').execute().get('files')[0].get('id')
    client_info_dict = gdrive.files().list(q=f'\'{nst_data_id}\' in parents', fields='files(id, name)', pageSize=1000).execute().get('files')

    # keyword analysis tool
    keyword_anal = Keywordanal()

    # BigQuery client
    bq = bigquery.Client()

    # dataframe columns
    df_columns = [
        'corporate_id', 'brand_id', 'date', 'keyword', 'keyword_type', 'category_1',
        'category_2', 'category_3', 'category_4', 'category_5', 'device_type', 'queries'
    ]

    # BigQuery table columns
    table_schema = [
        bigquery.SchemaField('corporate_id', 'STRING'),
        bigquery.SchemaField('brand_id', 'STRING'),
        bigquery.SchemaField('date', 'STRING'),
        bigquery.SchemaField('keyword', 'STRING'),
        bigquery.SchemaField('keyword_type', 'STRING'),
        bigquery.SchemaField('category_1', 'STRING'),
        bigquery.SchemaField('category_2', 'STRING'),
        bigquery.SchemaField('category_3', 'STRING'),
        bigquery.SchemaField('category_4', 'STRING'),
        bigquery.SchemaField('category_5', 'STRING'),
        bigquery.SchemaField('device_type', 'STRING'),
        bigquery.SchemaField('queries', 'INTEGER')
    ]

    print('Start to analyze keywords...', flush=True)
    for client in client_info_dict:
        client_id   = client['id']
        client_name = client['name']
        text        = 'Analyzing keywords for client : {}'.format(client_name)
        msg.append(text)
        print(text, flush=True)

        # get sheet file
        sheet = gspd.open_by_key(client_id).sheet1.get_all_records()

        # preprocess sheet data
        for idx in range(len(sheet)):
            sheet[idx]['keyword'] = sheet[idx]['keyword'].replace(' ', '').upper()
        sheet_data_list = [sheet[i:i+5] for i in range(0, len(sheet), 5)]
        
        # get table infomation
        table     = None
        table_id  = f'{PROJECT_NAME}.{client_name}.{TABLE_NAME}'
        try:
            table = bq.get_table(table_id)
        except NotFound:
            table    = bq.create_table(bigquery.Table(table_id, schema=table_schema))
            text     = 'New table created : {}'.format(table_id)
            msg.append(text)
            print(text, flush=True)

        # find latest date
        q = queries.find_latest_date.format(PROJECT_NAME, client_name, TABLE_NAME)
        q_result = bq.query(q).result()
        i_result = None

        # update table
        if (q_result.total_rows != 0):
            latest_date_dict = {}
            for row in q_result:
                if row.device_type not in latest_date_dict:
                    latest_date_dict[row.device_type] = {}
                latest_date_dict[row.device_type][row.keyword] = row.latest_date

            keyword_anal.set_latest_date_dict(latest_date_dict)

            df = pd.DataFrame(columns=df_columns)
            for chunk in sheet_data_list:
                keyword_list = [row.get('keyword', None) for row in chunk]
                keyword_dict = keyword_anal.get_keyword_anal_results(keyword_list)
                print(keyword_list, flush=True)

                for idx, row in enumerate(chunk):
                    pc_data = {
                        'corporate_id': row['corporate_id'],
                        'brand_id'    : row['brand_id'],
                        'date'        : keyword_dict[keyword_list[idx]]['dpc'].keys(),
                        'keyword'     : row['keyword'],
                        'keyword_type': row['keyword_type'],
                        'category_1'  : row['category_1'],
                        'category_2'  : row['category_2'],
                        'category_3'  : row['category_3'],
                        'category_4'  : row['category_4'],
                        'category_5'  : row['category_5'],
                        'device_type' : 'PC',
                        'queries'     : keyword_dict[keyword_list[idx]]['dpc'].values()
                    }
                    mo_data ={
                        'corporate_id': row['corporate_id'],
                        'brand_id'    : row['brand_id'],
                        'date'        : keyword_dict[keyword_list[idx]]['dmc'].keys(),
                        'keyword'     : row['keyword'],
                        'keyword_type': row['keyword_type'],
                        'category_1'  : row['category_1'],
                        'category_2'  : row['category_2'],
                        'category_3'  : row['category_3'],
                        'category_4'  : row['category_4'],
                        'category_5'  : row['category_5'],
                        'device_type' : '모바일',
                        'queries'     : keyword_dict[keyword_list[idx]]['dmc'].values()
                    }
                    df = pd.concat([df, pd.DataFrame(pc_data), pd.DataFrame(mo_data)])

            if (df.empty):
                text = '"{}" No change in data'.format(client_name) 
                print(text, flush=True)
                msg.append(text)
                continue
            else:
                print(df, flush=True)
                print('Inserting to BigQuery table...', flush=True)
                i_result = bq.insert_rows_from_dataframe(table=table, dataframe=df, selected_fields=table_schema)

        else:
            print('New table found.', flush=True)
            time_out = 0
            keyword_anal.set_latest_date_dict(latest_date_dict={})

            for chunk in sheet_data_list:
                keyword_list = [row.get('keyword', None) for row in chunk]
                keyword_dict = keyword_anal.get_keyword_anal_results(keyword_list)
                print(keyword_list, flush=True)

                df = pd.DataFrame(columns=df_columns)
                for idx, row in enumerate(chunk):
                    pc_data = {
                        'corporate_id': row['corporate_id'],
                        'brand_id'    : row['brand_id'],
                        'date'        : keyword_dict[keyword_list[idx]]['dpc'].keys(),
                        'keyword'     : row['keyword'],
                        'keyword_type': row['keyword_type'],
                        'category_1'  : row['category_1'],
                        'category_2'  : row['category_2'],
                        'category_3'  : row['category_3'],
                        'category_4'  : row['category_4'],
                        'category_5'  : row['category_5'],
                        'device_type' : 'PC',
                        'queries'     : keyword_dict[keyword_list[idx]]['dpc'].values()
                    }
                    mo_data ={
                        'corporate_id': row['corporate_id'],
                        'brand_id'    : row['brand_id'],
                        'date'        : keyword_dict[keyword_list[idx]]['dmc'].keys(),
                        'keyword'     : row['keyword'],
                        'keyword_type': row['keyword_type'],
                        'category_1'  : row['category_1'],
                        'category_2'  : row['category_2'],
                        'category_3'  : row['category_3'],
                        'category_4'  : row['category_4'],
                        'category_5'  : row['category_5'],
                        'device_type' : '모바일',
                        'queries'     : keyword_dict[keyword_list[idx]]['dmc'].values()
                    }
                    df = pd.concat([df, pd.DataFrame(pc_data), pd.DataFrame(mo_data)])
                print('Inserting to BigQuery table...', flush=True)

                while (True):
                    try:
                        i_result = bq.insert_rows_from_dataframe(table=table, dataframe=df, selected_fields=table_schema)
                        break
                    except NotFound:
                        print('not found table because of delay. please wait...', flush=True)
                        time_out += 1
                        sleep(0.5)
                        if (time_out > 50):
                            text = '"{}" BigQuery table not found'.format(client_name)
                            print(text, flush=True)
                            gmail.send_message(gmail.create_message(text, 'failed'))
                            exit()
                        continue

        if (type(i_result) is list):
            text = '{} Done'.format(client_name)
        else:
            text = '{} Failed'.format(client_name)
            status = 'failed'
        print(text, flush = True)
        msg.append(text)

    msg ='\n'.join(msg)
    gmail.send_message(gmail.create_message(msg, status))