import argparse
import telnetlib

from .monitor import MONITOR_HOST, MONITOR_PORT


def monitor_client(host, port):
    tn = telnetlib.Telnet()
    tn.open(host, port, timeout=0.5)
    try:
        tn.interact()
    except KeyboardInterrupt:
        pass
    finally:
        tn.close()


def main():
    parser = argparse.ArgumentParser("usage: python -m aiomonitor [options]")
    parser.add_argument("-H", "--host", dest="monitor_host",
                        default=MONITOR_HOST, type=str,
                        help="monitor host ip")

    parser.add_argument("-p", "--port", dest="monitor_port",
                        default=MONITOR_PORT, type=int,
                        help="monitor port number")
    args = parser.parse_args()
    monitor_client(args.monitor_host, args.monitor_port)


if __name__ == '__main__':
    main()
