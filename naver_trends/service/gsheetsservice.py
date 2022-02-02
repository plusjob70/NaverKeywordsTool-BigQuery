import gspread
from googleapiclient.discovery import build
from oauth2client.service_account import ServiceAccountCredentials
from naver_trends.common.uinfo import KEYPATH, GDRIVE_DIR_NAME

class GSheetsService:
    def __init__(self):
        self.creds = ServiceAccountCredentials.from_json_keyfile_name(
            filename=KEYPATH, 
            scopes=[
            'https://www.googleapis.com/auth/spreadsheets', 
            'https://www.googleapis.com/auth/drive'
            ]
        )
        self.drive = build('drive', 'v3', credentials=self.creds)
        self.sheet = gspread.authorize(credentials=self.creds)
    
    def get_all_files_info(self) -> list:
        data_id = self.drive.files().list(q=f'name=\'{GDRIVE_DIR_NAME}\'').execute().get('files')[0].get('id')
        return self.drive.files().list(q=f'\'{data_id}\' in parents', fields='files(id, name)', pageSize=1000).execute().get('files')

    def get_sheet(self, id):
        return self.sheet.open_by_key(id).sheet1.get_all_records()