#!/usr/bin/env python3

import time 
import os
import pika
import socket
import threading
import traceback
import json
import requests
from datetime import datetime
from base64 import b64encode

from deku import Deku
from mmcli_python.modem import Modem
from enum import Enum

from common.CustomConfigParser.customconfigparser import CustomConfigParser
from router import Router

# l_threads = {}
routing_consume_connection = None
routing_consume_channel = None
"""
publish_connection = None
publish_channel= None
"""

class Gateway(Router):

    def logger(self, text, _type='secondary', output='stdout', color=None, brightness=None):
        timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        color='\033[32m'
        if output == 'stderr':
            color='\033[31m'
        if _type=='primary':
            print(color + timestamp + f'* [{self.m_isp}|{self.m_index}] {text}')
        else:
            print(color + timestamp + f'\t* [{self.m_isp}|{self.m_index}] {text}')
        print('\x1b[0m')



    def __init__(self, m_index, m_isp, config, url, priority_offline_isp, ssl=None):
        super().__init__(url=url, priority_offline_isp=priority_offline_isp, ssl=ssl)
        self.m_index = m_index
        self.m_isp = m_isp
        self.config = config


    def watchdog_incoming(self):
        while(Deku.modem_ready(self.m_index)):
            # self.logger('checking for incoming messages...')
            messages=Modem(self.m_index).SMS.list('received')
            publish_connection, publish_channel = create_channel(
                    connection_url=config['GATEWAY']['connection_url'],
                    queue_name=config['GATEWAY']['routing_queue_name'],
                    blocked_connection_timeout=300,
                    durable=True)
            for msg_index in messages:
                sms=Modem.SMS(index=msg_index)


                ''' should this message be deleted or left '''
                ''' if deleted, then only the same gateway can send it further '''
                ''' if not deleted, then only the modem can send the message '''
                ''' given how reabbit works, the modem can't know when messages are sent '''
                msg=f"Publishing {msg_index}"
                self.logger(msg)
                try:
                    # routing_consume_channel.basic_publish(
                    publish_channel.basic_publish(
                            exchange='',
                            routing_key=config['GATEWAY']['routing_queue_name'],
                            body=json.dumps({"text":sms.text, "phonenumber":sms.number}),
                            properties=pika.BasicProperties(
                                delivery_mode=2))
                    ''' delete messages from here '''
                    ''' use mockup so testing can continue '''
                    # self.logger(f"Published...")
                except Exception as error:
                    log_trace(traceback.format_exc())
                else:
                    try:
                        Modem(self.m_index).SMS.delete(msg_index)
                    except Exception as error:
                        log_trace(traceback.format_exc(), show=True)

            messages=[]

            time.sleep(int(config['MODEMS']['sleep_time']))
        self.logger("disconnected", output='stderr') 
        if self.m_index in l_threads:
            del l_threads[self.m_index]

    """
    def start_consuming(self):
        wd = threading.Thread(target=self.watchdog_incoming, daemon=True)
        wd.start()
        wd.join()
    """



def log_trace(text, show=False, output='stdout', _type='primary'):
    timestamp = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    with open(os.path.join(os.path.dirname(__file__), 'service_files/logs', 'logs_node.txt'), 'a') as log_file:
        log_file.write(timestamp + " " +text + "\n\n")

    if show:
        color='\033[32m'
        if output == 'stderr':
            color='\033[31m'
        if _type=='primary':
            print(color + timestamp + f'* {text}')
        else:
            print(color + timestamp + f'\t* {text}')
        print('\x1b[0m')

def master_watchdog(config):
    shown=False
    global l_threads
    l_threads={}

    ''' instantiate configuration for all of Deku '''
    try:
        Deku()
        # configreader=CustomConfigParser()
        # config_event_rules=configreader.read("configs/events/rules.ini")
    except CustomConfigParser.NoDefaultFile as error:
        raise(error)
    except CustomConfigParser.ConfigFileNotFound as error:
        raise(error)
    except CustomConfigParser.ConfigFileNotInList as error:
        raise(error)
    else:
        while True:
            # if routing_consume_connection.is_closed or publish_connection.is_closed:
            """
            if routing_consume_connection.is_closed:
                print("* restarting connections...")
                rabbitmq_connection(config)
            """


            indexes=[]
            try:
                # indexes=Deku.modems_ready(ignore_lock=True)
                # indexes=Deku.modems_ready(remove_lock=True, ignore_lock=True)
                indexes=Deku.modems_ready(remove_lock=True)
                # indexes=['1', '2']
            except Exception as error:
                log_trace(error) 
                continue

            if len(indexes) < 1:
                # print(colored('* waiting for modems...', 'green'))
                if not shown:
                    print('* No Available Modem...')
                    shown=True
                time.sleep(int(config['MODEMS']['sleep_time']))
                continue

            shown=False
            # print('[x] starting consumer for modems with indexes:', indexes)
            for m_index in indexes:
                '''starting consumers for modems not already running,
                should be a more reliable way of doing it'''
                if m_index not in l_threads:
                    country=config['ISP']['country']
                    if not Deku.modem_ready(m_index):
                        continue
                    try:
                        m_isp = Deku.ISP.modems(operator_code=Modem(m_index).operator_code, country=country)
                    except Exception as error:
                        # print(error)
                        log_trace(error, show=True)
                        continue

                    try:
                        gateway=Gateway(m_index=m_index, m_isp=m_isp, config=config, url=config['ROUTER']['default'], priority_offline_isp=config['ROUTER']['isp'])
                        # print(outgoing_node, outgoing_node.__dict__)
                        gateway_thread=threading.Thread(target=gateway.watchdog_incoming, daemon=True)

                        # l_threads[m_index] = [outgoing_thread, routing_thread]
                        l_threads[m_index] = [gateway_thread]
                        # print('\t* Node created')
                    except pika.exceptions.ConnectionClosedByBroker:
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except pika.exceptions.AMQPChannelError as error:
                        # self.logger("Caught a chanel error: {}, stopping...".format(error))
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except pika.exceptions.AMQPConnectionError as error:
                        # self.logger("Connection was closed, should retry...")
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except socket.gaierror as error:
                        # print(error.__doc__)
                        # print(type(error))
                        # print(error)
                        # if error == "[Errno -2] Name or service not known":
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except CustomConfigParser.NoDefaultFile as error:
                        # print(traceback.format_exc())
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except CustomConfigParser.ConfigFileNotFound as error:
                        ''' with this implementation, it stops at the first exception - intended?? '''
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except CustomConfigParser.ConfigFileNotInList as error:
                        log_trace(traceback.format_exc(), output='stderr', show=True)
                    except Exception as error:
                        log_trace(traceback.format_exc(), output='stderr', show=True)

                    shown=False

            try:
                for m_index, thread in l_threads.items():
                    try:
                        # if not thread in threading.enumerate():
                        for i in range(len(thread)):
                            if thread[i].native_id is None:
                                print(f'* [{Modem(m_index).operator_name}|{m_index}] starting thread... ', end='')
                                thread[i].start()
                                print('Done')

                    except Exception as error:
                        log_trace(traceback.format_exc(), show=True)
            except Exception as error:
                log_trace(error)

            time.sleep(int(config['MODEMS']['sleep_time']))

def sms_routing_callback(ch, method, properties, body):
    # print(type(body))
    json_body = json.loads(body.decode('unicode_escape'))
    print(f'routing: {json_body}')
    # ch.basic_ack(delivery_tag=method.delivery_tag)

    ''' attempts both forms of routing, then decides if success or failed '''
    ''' checks config if for which state of routing is activated '''
    ''' if online only, if offline only, if both '''
    ''' also looks into which means of routing has been made available (which ISP if offline) '''
    # if Router.route( body.decode('utf-8')):
    if not "text" in json_body:
        log_trace('poorly formed message - text missing')
        ''' acks so that the message does not go back to the queue '''
        routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)
        return
    if not "phonenumber" in json_body:
        log_trace('poorly formed message - number missing')
        ''' acks so that the message does not go back to the queue '''
        routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)
        return

    def route_online(data):
        results = router.route_online(data=data)
        print(f"Routing results (ONLINE): {results.text} {results.status_code}")

    def route_offline(text, number):
        results = router.route_offline(text=text, number=number)
        print("* Routing results (OFFLINE) SMS successfully routed...")

    try:
        results=None
        json_data = json.dumps(json_body)
        # text_body = body.decode('unicode_escape')
        '''
        body is transmitted in base64 and should be decoded at the receiving end
        '''
        body = str(b64encode(body), 'unicode_escape')
        router_phonenumber=config['ROUTER']['router_phonenumber']
        # router = self.Router(url=config['ROUTER']['default'], priority_offline_isp=config['ROUTER']['isp'])
        if config['GATEWAY']['route_mode'] == Router.Modes.ONLINE.value:
            route_online(json_data)
            routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)

        elif config['GATEWAY']['route_mode'] == Router.Modes.OFFLINE.value:
            # results = router.route_offline(text=json_body['text'], number=router_phonenumber)
            route_offline(body, router_phonenumber)
            routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)

        elif config['GATEWAY']['route_mode'] == Router.Modes.SWITCH.value:
            try:
                route_online(json_data)
                routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)

            except Exception as error:
                try:
                    route_offline(body, router_phonenumber)
                    routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)
                except Exception as error:
                    # raise Exception(error)
                    log_trace(traceback.format_exc())
                    raise(error)
        else:
            print(f"Invalid routing protocol")
    except Router.MissingComponent as error:
        # print(error)
        ''' ack so that the messages don't go continue queueing '''
        routing_consume_channel.basic_ack(delivery_tag=method.delivery_tag)
        log_trace(traceback.format_exc())
    except ConnectionError as error:
        '''
        In the event of a network problem (e.g. DNS failure, refused connection, etc), Requests will raise a ConnectionError exception.
        '''
        routing_consume_channel.basic_reject( delivery_tag=method.delivery_tag, requeue=True)
    except requests.Timeout as error:
        '''
        If a request times out, a Timeout exception is raised.
        '''
        routing_consume_channel.basic_reject( delivery_tag=method.delivery_tag, requeue=True)
    except requests.TooManyRedirects as error:
        '''
        If a request exceeds the configured number of maximum redirections, a TooManyRedirects exception is raised.
        '''
        routing_consume_channel.basic_reject( delivery_tag=method.delivery_tag, requeue=True)
    except Exception as error:
        routing_consume_channel.basic_reject( delivery_tag=method.delivery_tag, requeue=True)
        log_trace(traceback.format_exc())
    finally:
        routing_consume_connection.sleep(3)

def create_channel(connection_url, queue_name, exchange_name=None, exchange_type=None, durable=False, binding_key=None, callback=None, prefetch_count=0, connection_port=5672, heartbeat=600, blocked_connection_timeout=None):
    credentials=None
    try:
        # TODO: port should come from config
        # parameters=pika.ConnectionParameters(connection_url, 5672, '/', credentials)
        """
        parameters=pika.ConnectionParameters(
                connection_url, 
                connection_port, 
                '/', 
                heartbeat=heartbeat, 
                blocked_connection_timeout=blocked_connection_timeout)
        """
        parameters=pika.ConnectionParameters(
                connection_url, 
                connection_port, 
                '/', 
                heartbeat=heartbeat)

        connection=pika.BlockingConnection(parameters=parameters)
        channel=connection.channel()
        channel.queue_declare(queue_name, durable=durable)
        channel.basic_qos(prefetch_count=prefetch_count)

        if binding_key is not None:
            channel.queue_bind(
                    exchange=exchange_name,
                    queue=queue_name,
                    routing_key=binding_key)

        if callback is not None:
            channel.basic_consume(
                    queue=queue_name,
                    on_message_callback=callback)

        return connection, channel
    except pika.exceptions.ConnectionClosedByBroker as error:
        raise(error)
    except pika.exceptions.AMQPChannelError as error:
        # self.logger("Caught a chanel error: {}, stopping...".format(error))
        raise(error)
    except pika.exceptions.AMQPConnectionError as error:
        # self.logger("Connection was closed, should retry...")
        raise(error)
    except socket.gaierror as error:
        # print(error.__doc__)
        # print(type(error))
        # print(error)
        # if error == "[Errno -2] Name or service not known":
        raise(error)


def rabbitmq_connection(config):
    # global publish_connection, publish_channel
    global routing_consume_connection
    global routing_consume_channel

    print("* starting rabbitmq connections... ", end="")
    try:
        routing_consume_connection, routing_consume_channel = create_channel(
                connection_url=config['GATEWAY']['connection_url'],
                callback=sms_routing_callback,
                durable=True,
                prefetch_count=1,
                # blocked_connection_timeout=300,
                queue_name=config['GATEWAY']['routing_queue_name'])

    except pika.exceptions.ConnectionClosedByBroker:
        log_trace(traceback.format_exc())
    except pika.exceptions.AMQPChannelError as error:
        # self.logger("Caught a chanel error: {}, stopping...".format(error))
        log_trace(traceback.format_exc())
    except pika.exceptions.AMQPConnectionError as error:
        # self.logger("Connection was closed, should retry...")
        log_trace(traceback.format_exc())
    except socket.gaierror as error:
        # print(error.__doc__)
        # print(type(error))
        # print(error)
        # if error == "[Errno -2] Name or service not known":
        log_trace(traceback.format_exc())
    except Exception as error:
        log_trace(traceback.format_exc())
    else:
        print("Done")

def start_consuming():
    try:
        ''' messages to be routed '''
        print('routing consumption starting...')
        routing_consume_channel.start_consuming() #blocking

    except pika.exceptions.ConnectionWrongStateError as error:
        # print(f'Request from Watchdog - \n\t {error}', output='stderr')
        log_trace(traceback.format_exc())
    except pika.exceptions.ChannelClosed as error:
        # print(f'Request from Watchdog - \n\t {error}', output='stderr')
        log_trace(traceback.format_exc())
    except Exception as error:
        # print(f'{self.me} Generic error...\n\t {error}', output='stderr')
        log_trace(traceback.format_exc())
    finally:
        print("Stopped consuming...")


if __name__ == "__main__":
    global config, router

    ''' checks for incoming messages and routes them '''
    config=None
    config=CustomConfigParser()
    config=config.read(".configs/config.ini")

    router = Router(url=config['ROUTER']['default'], priority_offline_isp=config['ROUTER']['isp'])

    rabbitmq_connection(config)
    thread_rabbitmq_connection = threading.Thread(target=routing_consume_channel.start_consuming, daemon=True)
    thread_rabbitmq_connection.start()

    """
    thread_master_watchdog = threading.Thread(target=master_watchdog, args=(config,), daemon=True)
    thread_master_watchdog.start()
    thread_rabbitmq_connection.join()
    """

    master_watchdog(config)
    thread_rabbitmq_connection.join()
    exit(0)
