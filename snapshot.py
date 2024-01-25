#!/usr/bin/env python3
import argparse
import configparser
import datetime
import logging
import os
import sys
import time
logging.basicConfig(level=logging.DEBUG)

import requests

'''
./snapshot.py test

Podanie jednego parametru, nazwy kamery, powoduje wczytanie konfiguracji dla kamery o danej nazwie z pliku config.ini


./snapshot.py test -i 57.128.196.32 -p 18100 -U admin -P abcd1234 -d /home/kamil/Pictures

Jeśli podany jest adres IP, informacje potrzebne do połączenia z kamerą pobieranie są z parametrów komendy


./snapshot.py -i 57.128.196.32 -p 18100 -U admin -P abcd1234 -d /home/kamil/Pictures

Nazwa może być pominięta


./snapshot.py -l

Wyświetlenie informacji o kamerach zapisanych w pliku config.ini
'''


def snapshot_dahua(host, port, username, password):
    url = 'http://{host}:{port}/cgi-bin/snapshot.cgi'.format(host=host, port=port)
    logging.info('connecting to camera')
    
    try:
        r = requests.get(url, auth=requests.auth.HTTPDigestAuth(username, password), timeout=5)
    except OSError:
        logging.warning('could not get picture, connection failed for host: {host}, port: {port}')
        return None
    except Exception as ex:
        logging.exception(ex)
    
    if r.status_code == 200:
        return r.content
    else:
        logging.warning('could not get picture, HTTP code {code} for host: {host}, port: {port}').format(code=r.status_code, host=host, port=port)
        return None
    

def snapshot_hikvision(host, port, username, password):
    url = 'http://{host}:{port}/ISAPI/Streaming/channels/101/picture'.format(host=host, port=port)
    logging.info('connecting to camera')
    try:
        r = requests.get(url, auth=requests.auth.HTTPDigestAuth(username, password), timeout=5)
    except OSError:
        logging.warning('could not get picture, connection failed for host: {host}, port: {port}').format(host=host, port=port)
        return None
    except Exception as ex:
        logging.exception(ex)
        return None
    
    if r.status_code == 200:
        return r.content
    else:
        logging.warning('could not get picture, HTTP code {code} for host: {host}, port: {port}'.format(code=r.status_code, host=host, port=port))
        return None


def snapshot_auto(host, port, username, password):
    img = snapshot_hikvision(host, port, username, password)
    if img is not None:
        return img
    return snapshot_dahua(host, port, username, password)


def save_image(img, dir, filename):
    try:
        full_path = os.path.join(dir, filename)
        logging.info('saving image to {}'.format(full_path))
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'wb') as f:
            f.write(img)

    except Exception as ex:
        logging.exception(ex)


def get_camera_info_by_name(name):
    config = configparser.ConfigParser()
    config.read('config.ini')
    model = config[name].get('model', 'auto')
    host = config[name]['host']
    port = config[name]['port']
    username = config[name]['username']
    password = config[name]['password']
    path = config['snapshot.exe']['dir']
    path = config[name].get('dir', path)

    return model, host, port, username, password, path


def main():
    parser = argparse.ArgumentParser(prog='snapshot.exe', description='IP camera snapshot tool')
    # parser.add_argument('-n', '--name', dest='name', type=str, help='IP camera name')
    parser.add_argument('name', nargs='?', type=str, help='IP camera name')
    parser.add_argument('-i', '--ip', dest='host', type=str, help='IP camera hostname/IP')
    parser.add_argument('-p', '--port', dest='port', type=int, help='IP camera port, default: 80', default=80)
    parser.add_argument('-U', '--username', dest='username', type=str, help='IP camera username')
    parser.add_argument('-P', '--password', dest='password', type=str, help='IP camera password')
    parser.add_argument('-m', '--model', dest='model', type=str, help='IP camera model', default='auto', choices=['hikvision', 'dahua', 'auto'])
    parser.add_argument('-d', '--dir', dest='path', type=str, help='save to directory, default: .', default='.')
    parser.add_argument('-l', '--list', dest='list_cameras', action='store_true', help='list cameras defined in config.ini')
    args = parser.parse_args()

    if args.list_cameras:
        config = configparser.ConfigParser()
        config.read('config.ini')

        for s in config.sections():
            if s == 'snapshot.exe':
                continue

            model, host, port, username, password, path = get_camera_info_by_name(s)

            print('')
            print(' name: {}'.format(s))
            print('model: {}'.format(model))
            print('   ip: {}'.format(host))
            print(' port: {}'.format(port))
            print('  dir: {}'.format(path))
        return

    name = args.name
    if args.host is not None:
        model, host, port, username, password, path = args.model, args.host, args.port, args.username, args.password, args.path
    else:
        model, host, port, username, password, path = get_camera_info_by_name(name)

    if model == 'hikvision':
        img = snapshot_hikvision(host, port, username, password)
    elif model == 'dahua':
        img = snapshot_dahua(host, port, username, password)
    elif model == 'auto':
        img = snapshot_auto(host, port, username, password)
    
    if img is not None:
        if name is not None:
            filename = '{}_{}.jpg'.format(name, datetime.datetime.now().replace(microsecond=0).isoformat())
        else:
            filename = '{}.jpg'.format(datetime.datetime.now().replace(microsecond=0).isoformat())
        save_image(img, path, filename)
    

if __name__ == '__main__':
    sys.exit(main())