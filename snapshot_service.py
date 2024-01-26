import configparser
import datetime
import logging
from logging import Formatter, Handler
import os
import sys
 
import cherrypy
import requests
import servicemanager
import win32event
import win32service
import win32serviceutil


if getattr(sys, 'frozen', False):
    application_path = os.path.dirname(sys.executable)
elif __file__:
    application_path = os.path.dirname(__file__)
__location__ = os.path.realpath(os.path.join(os.getcwd(), application_path))

CONFIG_FILE = os.path.join(__location__, 'config.ini')


def _configure_logging():
    formatter = Formatter('%(message)s')
    
    handler = _Handler()
    handler.setFormatter(formatter)
    
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


class _Handler(Handler):
    def emit(self, record):
        servicemanager.LogInfoMsg(record.getMessage())


def _main():
    
    _configure_logging()
    
    if len(sys.argv) == 1 and \
            sys.argv[0].endswith('.exe') and \
            not sys.argv[0].endswith(r'win32\PythonService.exe'):
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SnapshotService)
        servicemanager.StartServiceCtrlDispatcher()

    else:
        if len(sys.argv) == 2 and sys.argv[1] == 'help':
            sys.argv = sys.argv[:1]
             
        win32serviceutil.HandleCommandLine(SnapshotService)


def snapshot_dahua(host, port, username, password):
    url = 'http://{host}:{port}/cgi-bin/snapshot.cgi'.format(host=host, port=port)
    logging.info('connecting to camera')
    
    try:
        r = requests.get(url, auth=requests.auth.HTTPDigestAuth(username, password), timeout=5)
    except OSError:
        logging.warning('could not get picture, connection failed for host: {host}, port: {port}'.format(host=host, port=port))
        return None
    except Exception as ex:
        logging.exception(ex)
    
    if r.status_code == 200:
        return r.content
    else:
        logging.warning('could not get picture, HTTP code {code} for host: {host}, port: {port}'.format(code=r.status_code, host=host, port=port))
        return None
    

def snapshot_hikvision(host, port, username, password):
    url = 'http://{host}:{port}/ISAPI/Streaming/channels/101/picture'.format(host=host, port=port)
    logging.info('connecting to camera')
    try:
        r = requests.get(url, auth=requests.auth.HTTPDigestAuth(username, password), timeout=5)
    except OSError:
        logging.warning('could not get picture, connection failed for host: {host}, port: {port}'.format(host=host, port=port))
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
    config.read(CONFIG_FILE)
    model = config[name].get('model', 'auto')
    host = config[name]['host']
    port = config[name]['port']
    username = config[name]['username']
    password = config[name]['password']
    path = config['snapshot.exe']['dir']
    path = config[name].get('dir', path)

    return model, host, port, username, password, path


class Application:
    @cherrypy.expose
    def index(self):
        config = configparser.ConfigParser()
        config.read(CONFIG_FILE)

        response = 'configuration file: {}\r\n\r\n'.format(CONFIG_FILE)
        for s in config.sections():
            if s == 'snapshot.exe':
                continue

            model, host, port, _, _, path = get_camera_info_by_name(s)

            response += ' name: {}\r\n'.format(s)
            response += 'model: {}\r\n'.format(model)
            response += '   ip: {}\r\n'.format(host)
            response += ' port: {}\r\n'.format(port)
            response += '  dir: {}\r\n\r\n'.format(path)

        cherrypy.response.headers['Content-Type'] = 'text/plain'
        return response
    
    @cherrypy.expose
    def snapshot(self, name):
        try:
            model, host, port, username, password, path = get_camera_info_by_name(name)
        except Exception as ex:
            logging.exception(ex)

        if model == 'hikvision':
            img = snapshot_hikvision(host, port, username, password)
        elif model == 'dahua':
            img = snapshot_dahua(host, port, username, password)
        elif model == 'auto':
            img = snapshot_auto(host, port, username, password)

        cherrypy.response.headers['Content-Type'] = 'text/plain'

        ts = datetime.datetime.now().replace(microsecond=0).isoformat().replace(':', '').replace('-', '').replace('T', '_')
        if img is not None:
            if name is not None:
                filename = '{}_{}.jpg'.format(name, ts)
            else:
                filename = '{}.jpg'.format(ts)
            save_image(img, path, filename)

            return 'OK'
        else:
            return 'ERROR'


class SnapshotService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'QVMSSnapshotService'
    _svc_display_name_ = 'QVMS IP camera snapshot service'
    _svc_description_ = 'Captures camera snapshots.'
 
    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self._stop_event = win32event.CreateEvent(None, 0, 0, None)
 
    def GetAcceptedControls(self):
        result = win32serviceutil.ServiceFramework.GetAcceptedControls(self)
        result |= win32service.SERVICE_ACCEPT_PRESHUTDOWN
        return result

    def SvcDoRun(self):
        logging.info('Service started.')

        app = Application()
        cherrypy.tree.mount(app, '/')

        cherrypy.engine.start()
        while True:
            result = win32event.WaitForSingleObject(self._stop_event, 5000)
              
            if result == win32event.WAIT_OBJECT_0:
                # stop requested
                logging.info('Stopping service.')
                break
              
            else:
                # stop not requested
                # _log('is running')
                pass

        cherrypy.engine.exit()
        logging.info('Service stopped.')
        
    def SvcOtherEx(self, control, event_type, data):
        if control == win32service.SERVICE_CONTROL_PRESHUTDOWN:
            logging.info('Service received a pre-shutdown notification.')
            self.SvcStop()
        else:
            logging.info('Service received an event: code={}, type={}, data={}.'.format(
                    control, event_type, data))
    
    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self._stop_event)
 
    
if __name__ == '__main__':
    cherrypy.config.update({
        'log.screen': False,
        'log.access_file': '',
        'log.error_file': '',
        # 'server.socket_host': '127.0.0.1',
        'server.socket_port': 8888,
        # 'server.protocol_version': 'HTTP/1.1',
        # 'server.socket_timeout' : 300,
        'engine.autoreload.on': False})
    
    _main()