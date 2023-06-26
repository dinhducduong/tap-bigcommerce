#!/usr/bin/env python
from collections import Counter
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


def parse_date_string_arguments(fields):
    """
    Transforms specified input datetime arguments into a datetime object
    """

    if type(fields) is not list:
        fields = [fields]

    def decorator(method):
        @wraps(method)
        def parse_dt(*args, **kwargs):
            for key, value in kwargs.items():
                if key in fields:
                    if type(value) != str:
                        raise Exception((
                            "parse_date_string_arguments expects string value."
                            "{} provided"
                        ).format(value))
                    kwargs[key] = parse(value)
            return method(*args, **kwargs)
        return parse_dt

    return decorator


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

    def iterdates(self, start_date):
        for n in range(max(int((self.utcnow - start_date).days), 1)):
            start = start_date + timedelta(n)
            end = start_date + timedelta(n + 1)
            yield start, min(end, self.utcnow)

    @parse_date_string_arguments('bookmark')
    @validate
    def orders(self, replication_key, bookmark):

        for order in self.api.resource('orders', {
                'min_date_modified': bookmark.isoformat(),
                'sort': 'date_modified:asc'
        }):
            yield order

    @parse_date_string_arguments('bookmark')
    @validate
    def products(self, replication_key, bookmark):

        for product in self.api.resource('products', {
                'date_modified:min': bookmark.isoformat(),
                'sort': 'date_modified',
                'direction': 'asc'
        }):
            data = {
                "id": product['id'],
                "name": product['name'],
                "sku": product['sku'],
                "created_at": product['date_created'],
                "updated_at": product['date_modified'],
                "date_created": product['date_created'],
                "date_modified": product['date_modified'],
                "options": []
            }
            if "variants" in product:
                for variant in product['variants']:
                    variant_convert = {
                        "product_sku": variant['sku'],
                        "title": product['name'],
                        "price": variant['price'],
                        "values": [],
                    }
                    for option_value in variant['option_values']:
                        option_convert = {
                            "title": option_value['label'],
                            "option_type_id": option_value['option_id'],
                        }
                        variant_convert['values'].append(option_convert)
            yield data

    @parse_date_string_arguments('bookmark')
    @validate
    def products_attribute(self, replication_key, bookmark):

        for product in self.api.resource('products', {
                'date_modified:min': bookmark.isoformat(),
                'sort': 'date_modified',
                'direction': 'asc'
        }):
            data_convert = []
            if "options" in product:
                for option in product['options']:
                    data_option = {
                        "id": option['id'],
                        "attribute_id": option['id'],
                        "default_frontend_label": option['display_name'],
                        "default_value": option['display_name'],
                        "source": "bigcommerce",
                        "options": []
                    }
                    for value in option['option_values']:
                        data_option['options'].append({
                            "label": value['label'],
                            "value": value['label'],
                        })
                    data_convert.append(data_option)
                max_option_count = max(len(item["options"])
                                    for item in data_convert)
                name_counter = Counter(item["default_frontend_label"]
                                    for item in data_convert)
                unique_names = [name for name,
                                count in name_counter.items() if count == 1]
                final_objects = [
                    item for item in data_convert
                    if item["default_frontend_label"] in unique_names or len(item["options"]) == max_option_count
                ]
                yield final_objects

    def categories(self):

        for category in self.api.resource('categories'):
            yield category

    @parse_date_string_arguments('bookmark')
    @validate
    def customers(self, replication_key, bookmark):
        """
        Customers endpoint can't sort by date_modified, so resource
        is queried by day to ensure consistent replication key
        """

        for start, end in self.iterdates(bookmark):
            for customer in self.api.resource('customers', {
                    'min_date_modified': start.isoformat(),
                    'max_date_modified': end.isoformat()
            }):
                yield customer

    def coupons(self):

        for coupon in self.api.resource('coupons'):
            yield coupon
