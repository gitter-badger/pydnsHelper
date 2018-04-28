#!/usr/bin/env python
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
import random
import requests
import dns.dnssec
import dns.name
import dns.rdata
import dns.rdataclass
import dns.rdatatype
import dns.resolver
import dns.rrset


from urllib3.util import connection

__version__ = '0.0.2'

# cloudflare
# https://developers.cloudflare.com/1.1.1.1/dns-over-https/request-structure/
# curl 'https://cloudflare-dns.com/dns-query?ct=application/dns-json&name=google.com&type=A'
# - https://1.1.1.1/dns-query
# - https://1.0.0.1/dns-query
# google
# https://developers.google.com/speed/public-dns/docs/dns-over-https
# - https://dns.google.com/resolve

# domain to test dnssec verification: dnssec-failed.org

# response fields
# AD
# If true, it means that every record in the answer was verified with DNSSEC.
# CD
# If true, the client asked to disable DNSSEC validation.
# In this case, Cloudflare will still fetch the DNSSEC-related records, but it will not attempt to validate the records.

# Resource Record Types
A = 1
AAAA = 28
# DNS status codes
NOERROR = 0


UNRESERVED_CHARS = 'abcdefghijklmnopqrstuvwxyz' \
                   'ABCDEFGHIJKLMNOPQRSTUVWXYZ' \
                   '0123456789-._~'


class InvalidHostName(Exception):
    pass


_orig_create_connection = connection.create_connection


def patched_create_connection(address, *args, **kwargs):
    """Wrap urllib3's create_connection to resolve the name elsewhere"""
    # resolve hostname to an ip address; use your own
    # resolver here, as otherwise the system resolver will be used.
    host, port = address
    dnssec = DNSSEC()
    print(address)
    hostname = dnssec.resolveIPv4(host) # your_dns_resolver(host)
    return _orig_create_connection((hostname, port), *args, **kwargs)


connection.create_connection = patched_create_connection

class DNSSEC(object):

    def __init__(self):
        self.my_resolver = dns.resolver.Resolver()
        self.my_resolver.nameservers = ['1.1.1.1']

    def resolveIPv4(self, domain):
        ipv4answers = self.my_resolver.query(domain, 'A')
        for data in ipv4answers:
            print("DNSSEC: " + str(data))
        return str(ipv4answers[0])

    def resolveIPv6(self, domain):
        ipv6answers = self.my_resolver.query(domain, 'AAAA')
        for data in ipv6answers:
            print(data)
        return ipv6answers


class SecureDNS(object):

    def prepare_hostname(self, hostname):
        '''verify the hostname is well-formed'''
        hostname = hostname.rstrip('.')  # strip trailing dot if present

        if not(1 <= len(hostname) <= 253):  # test length of hostname
            raise InvalidHostName

        for label in hostname.split('.'):  # test length of each label
            if not(1 <= len(label) <= 63):
                raise InvalidHostName
        try:
            return hostname.encode('ascii')
        except UnicodeEncodeError:
            raise InvalidHostName


class SecureDNSCloudflare(SecureDNS):
    def __init__(
            self,
            query_type='A',
            ct='application/dns-json'
    ):
        self.url = 'https://cloudflare-dns.com/dns-query'
        self.params = {
            'type': query_type,
            'ct': ct
        }

    def resolve(self, hostname):
        '''return ip address(es) of hostname'''
        hostname = self.prepare_hostname(hostname)
        self.params.update({'name': hostname})

        r = requests.get(self.url, params=self.params)
        if r.status_code == 200:
            response = r.json()
            print(response)
            if response['Status'] == NOERROR:
                answers = []
                for answer in response['Answer']:
                    name, response_type, ttl, data = \
                        map(answer.get, ('name', 'type', 'ttl', 'data'))
                    if response_type in (A, AAAA):
                        answers.append(data)
                if answers == []:
                    return None
                return answers
        return None

class SecureDNSGoogle(SecureDNS):
    '''Resolve domains using Google's Public DNS-over-HTTPS API'''

    def __init__(
        self,
        query_type=1,
        cd=False,
        edns_client_subnet='0.0.0.0/0',
        random_padding=True,
    ):
        self.url = 'https://dns.google.com/resolve'
        self.params = {
            'type': query_type,
            'cd': cd,
            'edns_client_subnet': edns_client_subnet,
            'random_padding': random_padding,
        }

    def resolve(self, hostname):
        '''return ip address(es) of hostname'''
        hostname = self.prepare_hostname(hostname)
        self.params.update({'name': hostname})

        if self.params['random_padding']:
            padding = self.generate_padding()
            self.params.update({'random_padding': padding})

        r = requests.get(self.url, params=self.params)
        if r.status_code == 200:
            response = r.json()
            print(response)
            if response['Status'] == NOERROR:
                answers = []
                for answer in response['Answer']:
                    name, response_type, ttl, data = \
                        map(answer.get, ('name', 'type', 'ttl', 'data'))
                    if response_type in (A, AAAA):
                        answers.append(data)
                if answers == []:
                    return None
                return answers
        return None

    def generate_padding(self):
        '''generate a pad using unreserved chars'''
        pad_len = random.randint(10, 50)
        return ''.join(random.choice(UNRESERVED_CHARS) for _ in range(pad_len))


def main():
    dns1 = SecureDNSGoogle()
    result1 = dns1.resolve("nasa.gov")
    print(repr(result1))

    result2 = dns1.resolve("facebook.com")
    print(repr(result2))

    dns2 = SecureDNSCloudflare()
    result3 = dns2.resolve("nasa.gov")
    print(repr(result3))

    result4 = dns2.resolve("facebook.com")
    print(repr(result4))

    # dnssec = DNSSEC()
    # dnssec.resolveIPv4("cloudflare-dns.com")
    # dnssec.resolveIPv4("dns.google.com")


if __name__ == '__main__':
    main()
