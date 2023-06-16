#!/usr/bin/env python
from functools import wraps

import singer
from datetime import datetime, timedelta
from dateutil.parser import parse
from tap_bigcommerce.utilities import to_utc
from tap_bigcommerce.bigcommerce import Bigcommerce

logger = singer.get_logger().getChild('tap-bigcommerce')


def validate(method):

    @wraps(method)
    def _validate(*args, **kwargs):
        if 'replication_key' in kwargs and \
                kwargs['replication_key'] not in ['date_modified', 'id']:
            raise Exception("Client Error - invalid replication_key")

        if 'bookmark' in kwargs and \
                type(kwargs['bookmark']) is not datetime:
            raise Exception(
                "Client Error - bookmark must be valid datetime"
            )

        return method(*args, **kwargs)

    return _validate


class Client():

    authorized = False

    def is_authorized(self):
        return self.authorized is True


class BigCommerce(Client):

    def __init__(self, client_id, access_token, store_hash):
        self.client_id = client_id
        self.access_token = access_token
        self.store_hash = store_hash
        self.utcnow = singer.utils.now()
        self._reset_session()

    def _reset_session(self):
        try:
            self.api = Bigcommerce(
                client_id=self.client_id,
                store_hash=self.store_hash,
                access_token=self.access_token
            )
            self.authorized = True
        except Exception as e:
            self.authorized = False
            raise e

    @validate
    def orders(self, replication_key, bookmark):

        for order in self.api.resource('orders', {
                'min_date_modified': bookmark.isoformat(),
                'sort': 'date_modified:asc'
        }):
            yield order

    @validate
    def products(self, replication_key, bookmark):

        for product in self.api.resource('products', {
                'date_modified:min': bookmark.isoformat(),
                'sort': 'date_modified',
                'direction': 'asc'
        }):
            yield product

    @validate
    def customers(self, replication_key, bookmark):
        """
        Customers endpoint can't sort by date_modified, so resource
        is queried by day to ensure consistent replication key
        """

        for customer in self.api.resource('customers', {
        }):
            yield customer

    def coupons(self):

        for coupon in self.api.resource('coupons'):
            yield coupon
