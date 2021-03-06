# Copyright (C) 2018  Artur Fogiel
# This file is part of pyDNSHelper.
#
# pyDNSHelper is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# pyDNSHelper is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with pyDNSHelper.  If not, see <http://www.gnu.org/licenses/>.
import re
from time import sleep
from threading import Thread
from webui.models import Host
from django.db import IntegrityError, transaction


class HostsManager:
    def __init__(self):
        self.eng = None
        self.conn = None
        self.session = None
        self.threads = []
        self.do_monitor_ttl = True

    @staticmethod
    def block_site(url: str):
        HostsManager.remove_site(url)
        HostsManager.add_site(url=url, ttl=999)

    @staticmethod
    def unblock_site(url: str):
        HostsManager.remove_site(url)

    @staticmethod
    def get_ip(url: str):
        instance = Host.objects.filter(url=url).first()
        if instance:
            return instance.ip
        else:
            return None

    @staticmethod
    def add_site(url: str, comment: str="", ttl: int=60, ip: str='0.0.0.0'):
        if url == "" or url == "0.0.0.0":
            return

        if not Host.objects.filter(url=url).exists():
            Host.objects.create(ip=ip, url=url, ttl=ttl, comment=comment)

    @staticmethod
    def remove_site(url: str):
        if not Host.objects.filter(url=url).exists():
            instance = Host.objects.get(url=url)
            instance.delete()

    # TODO: add support for threads
    def import_host_files(self, path: str):
        from os import listdir
        from os.path import isfile, join
        onlyfiles = [f for f in listdir(path) if isfile(join(path, f))]
        for file in onlyfiles:
            print("File: " + file)
            with open(join(path, file), "r", encoding="utf-8") as hosts_file:
                with transaction.atomic():
                    for line in hosts_file:
                        HostsManager.add_imported_entry(line)

    @staticmethod
    def add_imported_entry(line: str):
        line = line.strip()
        if line.startswith("#"):
            return

        line = re.sub('[\t+]', '', line)
        line = re.sub('#', ' ', line)

        columns = line.split(' ')
        columns_nr = len(columns)
        url = columns[1] if columns_nr > 1 else None

        if url is not None:
            if HostsManager.get_ip(url) is not None:
                return

        if columns_nr > 2:
            HostsManager.add_site(url=url, comment=' '.join(columns[2:columns_nr]), ttl=999)
        elif columns_nr > 1:
            HostsManager.add_site(url, ttl=999)

    def start_ttl_monitoring(self):
        self.threads.append(Thread(target=self.monitor_ttl))
        self.threads[0].start()

    def monitor_ttl(self):
        print("Monitor started ...")
        while self.do_monitor_ttl:
            # select all non blocked urls
            query = Host.objects.order_by('ttl').filter(ttl__lt=999).all()
            for item in query:
                if item.ttl <= 0:
                    self.remove_site(item.url)
                else:
                    item.ttl -= 1
                    item.save()

            # wait one minute for next update
            sleep(60)

    @staticmethod
    def generate_host_file(output_path: str):
        all_entries = Host.objects.all()
        with open(output_path, "w", encoding="utf-8") as hosts_file:
            for host in all_entries:
                hosts_file.write(host.ip + " " + host.url + "\n")
