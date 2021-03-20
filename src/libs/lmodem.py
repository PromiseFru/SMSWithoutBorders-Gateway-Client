#!/bin/python

import subprocess
from subprocess import Popen, PIPE
from libs.lsms import SMS 
from ldatastore import Datastore 

import logging
import threading

class Modem(Datastore):
    details = {}

    def __init__( self, index:int):
        super().__init__()
        self.mmcli_m = ["mmcli", f"-Km", index]
        self.index = index

    def __bindObject( self, keys :list, value, _object=None):
        if _object == None:
            _object = {}

        if len(keys) > 1:
            if not keys[0] in _object:
                _object[keys[0]] = {}
            new_object = self.__bindObject(keys[1:], value, _object[keys[0]])
            # print(f"{len(keys)}: {new_object}")
            _object[keys[0]] = new_object
        else:
            _object = {keys[0] : value}
        return _object

    def __appendObject( self, kObject, tObject ):
        try:
            if type(tObject) == type(""):
                return {}
            if list(tObject.keys())[0] in kObject:
                key = list(tObject.keys())[0]
                new_object = self.__appendObject( kObject[key], tObject[key] )
                # print( new_object )
                if not new_object == {}:
                    kObject.update(new_object)
            else:
                kObject.update(tObject)
        except Exception as error:
            print(f"errtObject: ", tObject, type(tObject))
            print(error, "\n")

        return kObject


    def extractInfo(self, mmcli_output=None):
        try: 
            if mmcli_output == None:
                if hasattr(self, 'mmcli_m' ):
                    mmcli_output = subprocess.check_output(self.mmcli_m, stderr=subprocess.STDOUT).decode('utf-8')
                else:
                    raise Exception(f">> no input available to extract information")
        except subprocess.CalledProcessError as error:
            raise Exception(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
        else:
            # print(f"mmcli_output: {mmcli_output}")
            mmcli_output = mmcli_output.split('\n')
            self.details = {}
            for output in mmcli_output:
                m_detail = output.split(': ')
                if len(m_detail) < 2:
                    continue
                key = m_detail[0].replace(' ', '')
                self.details[key] = m_detail[1]

                indie_keys = key.split('.')
                # tmp_details = self.__bindObject( keys=indie_keys, value=m_detail[1] )
                tmp_details = self.__bindObject( keys=indie_keys, value=m_detail[1] )
                # print("tmp_details>> ", tmp_details)
                self.details = self.__appendObject(self.details, tmp_details)
                # print("self.details>> ", self.details)
                # self.details.update( tmp_details )
            # print("self.details:", self.details)
            return self.details

    def readyState(self):
        self.extractInfo()

        # if m_details[self.operator_code].isdigit() and m_details[self.signal_quality_value].isdigit() and m_details[self.sim] != '--':
        if self.details["modem"]["operator-code"].isdigit() and self.details["modem"]["signal-quality"]["value"].isdigit() and self.details["modem"]["generic"]["sim"] != "--":
            return True
        return False

    
    def __create(self, sms :SMS):
        mmcli_create_sms = []
        mmcli_create_sms += self.mmcli_m + sms.mmcli_create_sms
        mmcli_create_sms[-1] += '=number=' + sms.number + ",text='" + sms.text + "'"
        try: 
            mmcli_output = subprocess.check_output(mmcli_create_sms, stderr=subprocess.STDOUT).decode('utf-8').replace('\n', '')

        except subprocess.CalledProcessError as error:
            print(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
        else:
            print(f"{mmcli_output}")
            mmcli_output = mmcli_output.split(': ')
            creation_status = mmcli_output[0]
            sms_index = mmcli_output[1].split('/')[-1]
            if not sms_index.isdigit():
                print(f">> sms index isn't an index: {sms_index}")
            else:
                sms.index = sms_index
                # self.__send(sms)
        return sms

    def __send(self, sms: SMS):
        mmcli_send = self.mmcli_m + ["-s", sms.index, "--send"]
        state=None
        message=""
        status=""
        try: 
            mmcli_output = subprocess.check_output(mmcli_send, stderr=subprocess.STDOUT).decode('utf-8').replace('\n', '')

        except subprocess.CalledProcessError as error:
            returncode = error.returncode
            err_output = error.output.decode('utf-8').replace('\n', '')
            print(f">> failed to send sms")
            print(f"\treturn code: {returncode}")
            print(f"\tstderr: {err_output}")
            # raise Exception( error )
            state=False
            status='failed'
            message=err_output
            raise Exception({"state":state, "message":message, "status":status, "returncode":returncode})
        else:
            state=True
            status="sent"
            message=mmcli_output
            print(f"{mmcli_output}")

        return {"state":state, "message":message, "status":status}
            

    def set_sms(self, sms :SMS):
        self.sms = self.__create( sms )
        return self.sms

    def claim(self):
        try:
            self.extractInfo()
            new_message = self.acquire_message(modem_index=self.index, modem_imei=self.details["modem.3gpp.imei"])
        except Exception as error:
            raise( error )
        else:
            if not new_message==None:
                self.sms = SMS(messageID=new_message["id"])
                self.sms.create_sms( phonenumber=new_message["phonenumber"], text=new_message["text"] )
                return True
            else:
                return None

    def send_sms(self, sms :SMS, text=None, receipient=None):
        try:
            messageLogID = self.datastore.new_log(messageID=sms.messageID)
        except Exception as error:
            raise( error )
        else:
            try:
                if sms == None:
                    send_status=self.__send( self.sms )
                else:
                    send_status=self.__send( sms )
            except Exception as error:
                print(f">> Exception error:", error )
                sent_status = error

            self.datastore.update_log(messageLogID=messageLogID, status=send_status["status"], message=send_status["message"])
            if not send_status["state"]:
                logging.warn("[-] Failed to send...")
                self.datastore.release_message(sms.messageID)
                logging.warn("[-] Message released...")
                return False
            else:
                logging.info("[+] Message sent!")
                return True
