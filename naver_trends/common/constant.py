from datetime import datetime, timedelta

PC = 0
MO = 1

ID      = 0
SECRET  = 1
LICENSE = 2

IS_DANGEROUS_TIME   = '00:00' < datetime.now().strftime('%H:%M') < '10:30'
NOW                 = datetime.now()
YESTERDAY           = NOW - timedelta(days=1, hours=10, minutes=30)
DEFAULT_LATEST_DATE = datetime(2015, 12, 31)
DEFAULT_START_DATE  = datetime(2016, 1, 1, 10, 30, 0)