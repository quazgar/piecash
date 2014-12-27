# -*- coding: utf-8 -*-
from __future__ import print_function
from __future__ import division
from builtins import object
import datetime
from importlib import import_module
import os
from decimal import Decimal
import pytest
import shutil

from piecash import create_book, Account, ACCOUNT_TYPES, open_book, Price
from piecash._common import GnucashException
from piecash.core.account import _is_parent_child_account_types_consistent, root_types
from piecash.kvp import Slot

from test_helper import file_template_full, file_for_test_full, test_folder


@pytest.fixture
def session(request):
    s = create_book()
    return s


@pytest.fixture
def realbook_session(request):
    shutil.copyfile(file_template_full, file_for_test_full)

    # default session is readonly
    s = open_book(file_for_test_full)

    request.addfinalizer(lambda: os.remove(file_for_test_full))
    return s

class FooTestIntegration_ExampleScripts(object):
    def test_simple_book(self):
        import examples.simple_book
        print(examples.simple_book)

    def test_filtered_transaction_report(self):
        import examples.filtered_transaction_report
        print(examples.filtered_transaction_report)

    def test_simple_session(self):
        import examples.simple_session
        print(examples.simple_session)

    def test_simple_test(self):
        import examples.simple_test
        print(examples.simple_test)

    def test_simple_sqlite_create(self):
        import examples.simple_sqlite_create
        print(examples.simple_sqlite_create)

class TestIntegration_EmptyBook(object):
    def test_slots_create_access(self, session):
        kv = {
            "vint": 3,
            "vfl": 2.34,
            "vstr": "hello",
            "vdate": datetime.datetime.now().date(),
            "vtime": datetime.datetime.now(),
            "vnum": Decimal('4.53'),
            "vdct": {
                "spl": 2.3,
                "vfr": {
                    "vfr2": {
                        "foo": 33,
                        "baz": "hello"
                    },
                    "coo": Decimal('4.53')
                },
            }
        }
        for k, v in kv.items():
            session.book[k] = v
        session.save()

        for k, v in kv.items():
            assert k in session.book
            if isinstance(v, datetime.datetime):
                # check string format as the date in piecash is localized
                assert "{:%Y%m%d%h%M%s}".format(session.book[k].value) == "{:%Y%m%d%h%M%s}".format(v)
            else:
                assert session.book[k].value == v

    def test_slots_strings_access(self, session):
        b = session.book

        b["a/b/c/d/e"] = 1
        session.sa_session.flush()
        assert b["a"]["b"]["c"]["d"]["e"].value==1

        # b["a/b/c"] = {"d": {"t":"ko"}}

        b["a/b/c/d/f"] = "2"
        session.sa_session.flush()
        assert len(b["a"]["b"]["c"]["d"].slot_collection)==2

        b["a/b/c/d/f"] = "5"
        assert b["a"]["b/c"]["d"]["f"].value == "5"

        for k, v in b["a/b/c/d"].iteritems():
            assert k=="e" or k=="f"
        assert b["a/b/c/d"].get("e", "hello")==1
        assert b["a/b/c/d"].get("not there", "hello")=="hello"

        del b["a/b/c/d/e"]
        assert repr(b["a"])=="<SlotFrame a={'b': {'c': {'d': {'f': '5'}}}}>"

        with pytest.raises(TypeError):
            b["a/b/c/d/f"] = 4
        with pytest.raises(TypeError):
            b["a/b/c"] = True

        assert {n for (n,) in session.sa_session.query(Slot._name)} == {'a' ,'a/b','a/b/c','a/b/c/d','a/b/c/d/e','a/b/c/d/f'}


        # delete some elements
        del b["a"]["b"][:]
        session.sa_session.flush()
        assert {n for (n,) in session.sa_session.query(Slot._name)} == {'a' ,'a/b'}

        session.sa_session.flush()
        assert len(b["a"].slot_collection)==1
        assert len(b["a/b"].slot_collection)==0

        with pytest.raises(KeyError):
            b["a/b/c"]

        del b["a"]["b"]
        session.sa_session.flush()
        assert len(b["a"].slot_collection)==0

        del b[:]
        session.sa_session.flush()
        assert {n for (n,) in session.sa_session.query(Slot._name)} == set([])



    def test_empty_gnucash_file(self, session):
        accs = session.accounts

        assert len(accs) == 0
        assert all(acc.parent is None for acc in accs)
        assert all(acc.account_type == "ROOT" for acc in accs)

    def test_is_parent_child_account_types_consistent(self):
        combi_OK = [
            ("ROOT", "BANK"),
            (None, "ROOT"),
            ("ROOT", "EQUITY"),
            ("ROOT", "ASSET"),
            ("ROOT", "EXPENSE"),
        ]

        combi_not_OK = [
            ("ROOT", "ROOT"),
            ("ROOT", None),
            (None, "ASSET"),
            ("ASSET", "EQUITY"),
            ("EQUITY", "ASSET"),
            ("ASSET", "INCOME"),
            ("EXPENSE", "ASSET"),
        ]

        for p, c in combi_OK:
            assert _is_parent_child_account_types_consistent(p, c)

        for p, c in combi_not_OK:
            assert not _is_parent_child_account_types_consistent(p, c)

    def test_add_account_compatibility(self, session):
        # test compatibility between child account and parent account
        for acc_type1 in ACCOUNT_TYPES - root_types:
            acc1 = Account(name=acc_type1, account_type=acc_type1, parent=session.book.root_account, commodity=None)

            for acc_type2 in ACCOUNT_TYPES:

                if not _is_parent_child_account_types_consistent(acc_type1, acc_type2):
                    with pytest.raises(ValueError):
                        acc2 = Account(name=acc_type2, account_type=acc_type2, parent=acc1, commodity=None)
                else:
                    acc2 = Account(name=acc_type2, account_type=acc_type2, parent=acc1, commodity=None)

        session.save()

        assert len(session.accounts) == 100

    def test_add_account_names(self, session):
        # raise ValueError as acc1 and acc2 shares same parents with same name
        acc1 = Account(name="Foo", account_type="MUTUAL", parent=session.book.root_account, commodity=None)
        acc2 = Account(name="Foo", account_type="BANK", parent=session.book.root_account, commodity=None)
        with pytest.raises(ValueError):
            session.save()
        session.sa_session.rollback()
        # ok as same name but different parents
        acc3 = Account(name="Fooz", account_type="BANK", parent=session.book.root_account, commodity=None)
        acc4 = Account(name="Fooz", account_type="BANK", parent=acc3, commodity=None)
        session.save()
        # raise ValueError as now acc4 and acc3 shares same parents with same name
        acc4.parent = acc3.parent
        with pytest.raises(ValueError):
            session.save()


    def test_example(self, realbook_session):
        session = realbook_session
        book = session.book

        # example 1, print all stock prices in the Book
        # display all prices
        for price in session.query(Price).all():
            print("{}/{} on {} = {} {}".format(price.commodity.namespace,
                                               price.commodity.mnemonic,
                                               price.date,
                                               float(price.value_num) / price.value_denom,
                                               price.currency.mnemonic,
            ))

        for account in session.accounts:
            print(account)

        # build map between account fullname (e.g. "Assets:Current Assets" and account)
        map_fullname_account = {account.fullname: account for account in session.query(Account).all()}

        # use it to retrieve the current assets account
        acc_cur = map_fullname_account["Assets:Current Assets"]

        # retrieve EUR currency
        EUR = session.commodities.get(mnemonic='EUR')

        # add a new subaccount to this account of type ASSET with currency EUR
        Account(name="new savings account", account_type="ASSET", parent=acc_cur, commodity=EUR)

        # save changes
        with pytest.raises(GnucashException) as excinfo:
            session.save()
