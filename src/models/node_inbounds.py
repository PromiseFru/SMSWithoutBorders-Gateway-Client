#!/usr/bin/env python3

from __future__ import annotations

import os
import configparser
import logging 
import pika
import time
import json
import threading
import base64

from common.mmcli_python.modem import Modem
from deku import Deku
from rabbitmq_broker import RabbitMQBroker
from seeds import Seeds
from seeders import Seeders
import helpers

class NodeInbound(threading.Event):
    locked_modems = True

    def __init__(self, modem:Modem, 
            daemon_sleep_time:int=3)->None:

        super().__init__()
        self.modem = modem
        self.daemon_sleep_time = daemon_sleep_time

    @staticmethod
    def init(modem:Modem, daemon_sleep_time:int=3)->NodeOutgoing:
        """Create an instance of :cls:NodeOutgoing.

            Args:
                modem: Instanstiates a node for this modem.
                daemon_sleep_time: Sleep time for each modem.
                active_nodes: from :cls:ModemManager to manage active nodes.
        """
        nodeIncoming = NodeInbound(modem, daemon_sleep_time)
        return nodeIncoming

    def __publish_to_broker__(self, sms:str, queue_name:str)->None:
        try:
            publish_data = {"text":sms.text, "number":sms.number}
            self.publish_channel.basic_publish(
                    exchange='',
                    routing_key=queue_name,
                    body=json.dumps(publish_data),
                    properties=pika.BasicProperties(
                        delivery_mode=2))
            logging.debug("published %s", publish_data)
        except Exception as error:
            raise error


    def listen_for_sms_inbound(self, publish_url:str='localhost', queue_name:str='inbound.route.route' )->None:
        while True:
            if ( not hasattr(self, 'publish_connection') or 
                    self.publish_connection.is_closed):

                logging.debug("creating new connection for publishing")

                self.publish_connection, self.publish_channel = \
                        RabbitMQBroker.create_channel(
                            connection_url=publish_url,
                            queue_name=queue_name,
                            heartbeat=600,
                            blocked_connection_timeout=60,
                            durable=True)

            inbound_messages = self.modem.SMS.list('received')
            for msg_index in inbound_messages:
                sms=Modem.SMS(index=msg_index)
                logging.debug("Number:%s, Text:%s", 
                        sms.number, sms.text)

                try:
                    data = {"MSISDN":sms.number, "IMSI":self.modem.get_sim_imsi(), "text":sms.text}
                    """
                    Checks if record exist in ledger (ledger already exist)
                    If not exist, check if inbound is for ledger
                    If for ledger insert record in ledger and continue (Number has been acquired)
                    """
                    logging.debug("checking if data is ledger")

                    ledger = Ledger(['clients'])

                    if not ledger.client_record_exist(data=data):
                        if self.is_ledger_request(data):
                            ledger.insert_client_record(data)
                            logging.debug("Created new ledger")
                        else:
                            logging.debug("Not a ledger command")
                    else:
                        logging.debug("record exist, continuing to publish")
                except Exception as error:
                    logging.exception(error)
                
                try:
                    self.__publish_to_broker__(sms=sms, queue_name=queue_name)
                except Exception as error:
                    # self.logging.critical(error)
                    raise error

                else:
                    try:
                        self.modem.SMS.delete(msg_index)
                    except Exception as error:
                        raise error
                    '''
                    else:
                        try:
                            self.__exec_remote_control__(sms)
                        except Exception as error:
                            # self.logging.exception(traceback.format_exc())
                            raise error
                    '''
            # inbound_messages=[]
            time.sleep(self.daemon_sleep_time)


    def make_seeder_request(seeder: Seeder):
        """Sends a request to the provided seeder.
        """
        text = json.dumps({"IMSI": self.modem.get_sim_imsi()})

        text = str(base64.b64encode(str.encode(text)), 'utf-8')

        logging.debug("+ making request to seeder: %s %s", 
                seeder.MSISDN, text)

        try:
            Deku.modem_send(
                    modem=self.modem,
                    number=seeder.MSISDN,
                    text=text,
                    force=True)
        except Exception as error:
            raise error
        else:
            try:
                seeder.update_state('requested')
                logging.debug("Seeder %s state changed to requested", seeder._id)
            except Exception as error:
                raise error

    def main(self, seeder=False) -> None:

        """Monitors modems for inbound messages and publishes.

        This is process is blocking.

            Args:
                publish_url:
                    url of local rabbitmq broker.

                queue_name:
                    name of queue on rabbitmq where messages for routing
                    should routed to.
        """

        logging.debug("monitoring inbound messages")

        try:
            IMSI= self.modem.get_sim_imsi()
            self.seed = Seeds(IMSI=IMSI, seeder=seeder)
            if not self.seed.is_seed():
                logging.debug("[%s] is not a seed... fetching remote seeders", self.seed.IMSI)
                seeders = Seeders.request_remote_seeders()

                if len(seeders) < 1:
                    logging.debug("No remote seeders found, checking for hardcoded")

                    # Important: Should never be empty
                    seeders = Seeders.request_hardcoded_seeders()
                else:
                    logging.debug("%d remote seeders found", len(seeders))

                filtered_seeders = Seeders._filter(seeders, 
                        {"country":helpers.get_modem_operator_country(self.modem),
                            "operator_name":helpers.get_modem_operator_name(self.modem)})

                if not filtered_seeders:
                    logging.debug("No seeders found for filter, trying with lesser filters")
                    filtered_seeders = Seeders._filter(seeders, 
                            {"country":helpers.get_modem_operator_country(self.modem)})
                else:
                    logging.debug("%d filtered seeders found!", len(filtered_seeders))

                if len(filtered_seeders) > 0:
                    logging.debug("%d filtered seeders found!", len(filtered_seeders))
                    seeder = filtered_seeders[0]
                else:
                    logging.debug("no seeders found, falling back to hardcoded ones")
                    seeder = seeders[0]

                try:
                    logging.debug("making seeder request [%s]", seeder.MSISDN)
                    self.make_seeder_request(seeder=seeder)
                except Exception as error:
                    raise error
                else:
                    logging.info("Seed request made successfully!")
            else:
                logging.info("Node is valid seed!")

        except Exception as error:
            raise error
        else:
            try:
                logging.info("[%s | %s] starting incoming listener", self.modem.imei, self.modem.get_operator_name())
                inbound_thread = threading.Thread(
                        target=self.listen_for_sms_inbound, 
                        daemon=True)
                inbound_thread.start()

                self.wait()
                logging.debug("stopping inbound listener")

            except Modem.MissingModem as error:
                logging.exception(error)

            except Modem.MissingIndex as error:
                logging.exception(error)

            except Exception as error:
                logging.exception(error)

            finally:
                time.sleep(self.daemon_sleep_time)
