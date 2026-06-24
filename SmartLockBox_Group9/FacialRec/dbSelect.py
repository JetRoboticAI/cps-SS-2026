import sqlite3 as sql
import pandas as pd

class DBSelect:
    def __init__(self) -> None:
        self.sqlConnect()
        
    def sqlConnect(self):
        self.conn = sql.connect("lockbox.db")
        self.cursor = self.conn.cursor()

    def seeTable(self):
        self.data = pd.read_sql_query("SELECT * FROM LOGS",self.conn)
        print(self.data)

if __name__ == "__main__":
    db = DBSelect()
    db.seeTable()