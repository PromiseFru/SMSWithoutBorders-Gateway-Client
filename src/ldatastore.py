#!/bin/python import mysql.connector
import mysql.connector
import pymysql
from datetime import date

# rewrite message store to allow for using as a class extension
class Datastore(object):
    def __init__(self, configs_filepath=None ):
        import configparser
        self.CONFIGS = configparser.ConfigParser(interpolation=None)

        if configs_filepath==None:
            self.CONFIGS.read("libs/config.ini")
        else:
            self.CONFIGS.read(configs_filepath)

        self.HOST = self.CONFIGS["MYSQL"]["HOST"]
        self.USER = self.CONFIGS["MYSQL"]["USER"]
        self.PASSWORD = self.CONFIGS["MYSQL"]["PASSWORD"]
        self.DATABASE = self.CONFIGS["MYSQL"]["DATABASE"]

        self.conn = pymysql.connect( host=self.HOST, user=self.USER, password=self.PASSWORD, database=self.DATABASE, cursorclass=pymysql.cursors.SSDictCursor)
        # self.cursor = self.conn.cursor(buffered=True)
        self.cursor = self.conn.cursor()

    def new_log(self, messageID):
        query=f"INSERT INTO logs SET messageID={messageID}"
        try:
            self.cursor.execute( query )
            messageLogID = self.conn.commit()

        except mysql.connector.Error as err:
            raise Exception( err )
        else:
            return messageLogID

    def update_log(self, messageLogID:int, status:str, message:str):
        query=f"UPDATE logs SET status={status}, message={message} WHERE id={messageLogID}"
        try:
            self.cursor.execute( query )
            messageLogID = self.conn.commit()

        except mysql.connector.Error as err:
            raise Exception( err )
        else:
            return messageLogID

    def release_message(self, messageID:int):
        query=f"UPDATE messages SET claimed_modem_imei=NULL WHERE id={messageID}"
        try:
            self.cursor.execute( query )
            messageID = self.conn.commit()

        except mysql.connector.Error as err:
            raise Exception( err )
        else:
            return messageID

    def claim_message(self, messageID:int, modem_imei:str):
        query=f"UPDATE messages SET claimed_modem_imei={modem_imei} WHERE id={messageID}"
        print(f"Claiming: {query}")
        try:
            self.cursor.execute( query )
            # messageID = self.conn.commit()

        except mysql.connector.Error as err:
            raise Exception( err )
        else:
            return messageID

    def acquire_message(self, modem_index:int, modem_imei:str):
        '''
            TODO: 
                - Filter by last come first out
        '''

        query = f"SELECT * FROM messages where claimed_modem_imei is NULL LIMIT 1"
        try:
            self.cursor.execute( query )
            sms_message = self.cursor.fetchall()
            # print(sms_message, type(sms_message), len(sms_message))
            counter = 0
            mn_sms_message = None
            for row in sms_message:
                messageID = row["id"]
                print(row["text"], messageID)
                self.claim_message(messageID, modem_imei)
                
                if counter < 1:
                    mn_sms_message = row
                    ++counter

            return mn_sms_message

        except mysql.connector.Error as err:
            raise Exception( err )


    def new_message(self, text:str, phonenumber:str, isp:str):
        query = f"INSERT INTO messages SET text='{text}', phonenumber='{phonenumber}', isp='{isp}'"
        try:
            self.cursor.execute( query )
            self.conn.commit()
            messageID = self.cursor.lastrowid
            # messageID = self.conn.commit()
        except mysql.connector.Error as err:
            raise Exception( err )
        else:
            return messageID

'''
    def fetch_for( data :dict):
        query = f"SELECT * FROM {tb_messages} WHERE "
        for key, value in data:

            appended=False
            # if one key needs to or many values
            if type(value)==type({}):
                query += "("
                _appended=False
                for _key, _value in value:
                    if _appended:
                        query += "OR "
                    if type(_value)==type(0): #int
                        query += f"{key}={value} "
                    else:
                        query += f"{key}='{value}' "
                    _appended=True
                query += ") "
            if appended:
                query+= "AND "
            if type(_value)==type(0): #int
                query += f"{key}={value} "
            else:
                query += f"{key}='{value}' "
            appended=True

        query += "WHERE state='pending' ORDER BY date DESC LIMIT 1"
'''