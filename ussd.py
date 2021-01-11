#!/bin/python
import subprocess
import re
from modem import Modem 

class USSD():
    def __init__(self, modem):
        self.modem = modem

    def initiate(self, command):
        ussd_command = self.modem.mmcli_m + [f"--3gpp-ussd-initiate={command}"]
        # print( ussd_command )
        try: 
            mmcli_output = subprocess.check_output(ussd_command, stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as error:
            # print(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
            raise Exception(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
        else:
            # remote 'new reply from network:'
            mmcli_output = mmcli_output.split(": ", 1)[1].split("'")[1]
            # print( mmcli_output )
            return mmcli_output

    def respond(self, command):
        ussd_command = self.modem.mmcli_m + [f"--3gpp-ussd-respond={command}"]
        try: 
            mmcli_output = subprocess.check_output(ussd_command, stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as error:
            # print(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
            raise Exception(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
        else:
            # remote 'new reply from network:'
            # print( mmcli_output )
            mmcli_output = mmcli_output.split(": '", 1)[1][:-1]
            return mmcli_output

    def cancel(self):
        ussd_command = self.modem.mmcli_m + [f"--3gpp-ussd-cancel"]
        try: 
            mmcli_output = subprocess.check_output(ussd_command, stderr=subprocess.STDOUT).decode('utf-8')
        except subprocess.CalledProcessError as error:
            # print(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
            raise Exception(f"[stderr]>> return code[{error.returncode}], output[{error.output.decode('utf-8')}")
        else:
            return True
        
        return False

    def status(self):
        ussd_command = self.modem.mmcli_m + [f"--3gpp-ussd-status"]


if __name__ == "__main__":
    modem = Modem("0")
    ussd = USSD(modem)
    try:
        respond = ussd.initiate( "*123#" )
        print(respond)

        respond = ussd.respond( "6" )
        print(respond)

        respond = ussd.respond( "4" )
        print(respond)

        ussd.cancel()
    except Exception as error:
        print( error )