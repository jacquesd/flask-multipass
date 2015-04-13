# This file is part of Flask-MultiAuth.
# Copyright (C) 2015 CERN
#
# Flask-MultiAuth is free software; you can redistribute it
# and/or modify it under the terms of the Revised BSD License.

from __future__ import unicode_literals

from pkg_resources import EntryPoint

import pytest
from flask import Flask

from flask_multiauth import MultiAuth
from flask_multiauth._compat import iteritems, add_metaclass
from flask_multiauth.auth import AuthProvider
from flask_multiauth.core import _MultiAuthState
from flask_multiauth.exceptions import AuthenticationFailed
from flask_multiauth.identity import IdentityProvider
from flask_multiauth.util import (classproperty, get_state, resolve_provider_type, map_provider_data, login_view,
                                  get_canonical_provider_map, validate_provider_map, SupportsMeta, get_provider_base,
                                  map_app_data)


@pytest.mark.parametrize(('config_map', 'canonical_map'), (
    ({'foo': 'bar'},                                 {'foo': ({'identity_provider': 'bar'},)}),
    ({'foo': ['bar']},                               {'foo': ({'identity_provider': 'bar'},)}),
    ({'foo': {'bar'}},                               {'foo': ({'identity_provider': 'bar'},)}),
    ({'foo': {'identity_provider': 'bar'}},          {'foo': ({'identity_provider': 'bar'},)}),
    ({'foo': [{'identity_provider': 'bar'}]},        {'foo': ({'identity_provider': 'bar'},)}),
    ({'foo': [{'identity_provider': 'bar'}, 'moo']}, {'foo': ({'identity_provider': 'bar'},
                                                              {'identity_provider': 'moo'})}),
    ({'foo': 'bar', 'meow': 'moo'},                  {'foo': ({'identity_provider': 'bar'},),
                                                      'meow': ({'identity_provider': 'moo'},)}),
))
def test_get_canonical_provider_map(config_map, canonical_map):
    assert get_canonical_provider_map(config_map) == canonical_map


def test_get_state_app_not_initialized():
    app = Flask('test')
    with pytest.raises(AssertionError):
        get_state(app)


def test_get_state_explicit():
    app = Flask('test')
    app2 = Flask('test2')
    multiauth = MultiAuth()
    multiauth.init_app(app)
    multiauth.init_app(app2)
    # outside app ctx
    with pytest.raises(RuntimeError):
        assert get_state().app
    # explicit app
    assert get_state(app2).app is app2
    # explicit app inside other app context (unlikely)
    with app.app_context():
        assert get_state(app2).app is app2


def test_get_state():
    app = Flask('test')
    multiauth = MultiAuth(app)
    with app.app_context():
        state = get_state(app)
        assert state.multiauth is multiauth
        assert state.app is app
        assert get_state(app) is state


@pytest.mark.parametrize(('provider_data', 'mapping', 'key_filter', 'result'), (
    ({'pk1': 'a'},             {},                           None,           {'pk1': 'a'}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1'},               None,           {'ak1': 'a', 'pk2': 'b'}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk3'}, None,           {'ak1': 'a', 'ak2': None, 'pk2': 'b'}),
    ({'pk1': 'a'},             {},                           [],             {}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1'},               ['ak1', 'ak1'], {'ak1': 'a'}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk3'}, {'ak1'},        {'ak1': 'a'}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk3'}, {'ak1', 'pk2'}, {'ak1': 'a', 'pk2': 'b'}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk3'}, {'ak1', 'ak2'}, {'ak1': 'a', 'ak2': None}),
    ({'pk1': 'a', 'pk2': 'b'}, {'ak1': 'pk1'},               {'ak1', 'ak2'}, {'ak1': 'a', 'ak2': None}),
))
def test_map_provider_data(provider_data, mapping, key_filter, result):
    assert map_provider_data(provider_data, mapping, key_filter) == result


@pytest.mark.parametrize(('app_data', 'mapping', 'key_filter', 'result'), (
    ({},                       {},                           None, {}),
    ({},                       {},                           {},   {}),
    ({},                       {'ak1': 'pk1'},               None, {}),
    ({'ak1': 'a'},             {},                           None, {'ak1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1'},               None, {'pk1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1', 'ak2': 'pk2'}, None, {'pk1': 'a'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1'},               None, {'pk1': 'a', 'ak2': 'b'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk2'}, None, {'pk1': 'a', 'pk2': 'b'}),
    ({},                       {'ak1': 'pk1'},               {'ak1'}, {}),
    ({'ak1': 'a'},             {},                           {'ak1'}, {'ak1': 'a'}),
    ({'ak1': 'a'},             {},                           {'ak2'}, {}),
    ({'ak1': 'a'},             {},                           {'ak1', 'ak2'}, {'ak1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1'},               {'ak1'}, {'pk1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1'},               {'ak2'}, {}),
    ({'ak1': 'a'},             {'ak1': 'pk1'},               {'ak1', 'ak2'}, {'pk1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak1'}, {'pk1': 'a'}),
    ({'ak1': 'a'},             {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak2'}, {}),
    ({'ak1': 'a'},             {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak1', 'ak2'}, {'pk1': 'a'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1'},               {'ak1'}, {'pk1': 'a'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1'},               {'ak2'}, {'ak2': 'b'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1'},               {'ak3'}, {}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1'},               {'ak1', 'ak2'}, {'pk1': 'a', 'ak2': 'b'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak1'}, {'pk1': 'a'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak2'}, {'pk2': 'b'}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak3'}, {}),
    ({'ak1': 'a', 'ak2': 'b'}, {'ak1': 'pk1', 'ak2': 'pk2'}, {'ak1', 'ak2'}, {'pk1': 'a', 'pk2': 'b'}),
))
def test_map_app_data(app_data, mapping, key_filter, result):
    assert map_app_data(app_data, mapping, key_filter) == result


def test_get_provider_base():
    class SomeAuthProvider(AuthProvider):
        pass

    class NestedAuthProvider(SomeAuthProvider):
        pass

    class SomeIdentityProvider(IdentityProvider):
        pass

    assert get_provider_base(SomeAuthProvider) is AuthProvider
    assert get_provider_base(NestedAuthProvider) is AuthProvider
    assert get_provider_base(SomeIdentityProvider) is IdentityProvider


def test_get_provider_base_invalid():
    class NoProvider(object):
        pass

    class InvalidProvider(AuthProvider, IdentityProvider):
        pass

    pytest.raises(TypeError, get_provider_base, NoProvider)
    pytest.raises(TypeError, get_provider_base, InvalidProvider)


def test_login_view(mocker):
    handle_auth_error = mocker.patch.object(MultiAuth, 'handle_auth_error')
    app = Flask('test')
    e = AuthenticationFailed()

    @app.route('/ok')
    @login_view
    def ok():
        return ''

    @app.route('/err')
    @login_view
    def err():
        raise Exception()

    @app.route('/fail')
    @login_view
    def fail():
        raise e

    MultiAuth(app)
    with app.test_client() as c:
        c.get('/ok')
        assert not handle_auth_error.called
        c.get('/err')
        assert not handle_auth_error.called
        c.get('/fail')
        handle_auth_error.assert_called_with(e, True)


class DummyBase(object):
    _entry_point = 'dummy'


class Dummy(DummyBase):
    pass


class FakeDummy(object):
    pass


class MockEntryPoint(EntryPoint):
    def load(self, *args, **kwargs):
        mapping = {
            'dummy': Dummy,
            'fake': FakeDummy,
        }
        return mapping[self.name]


@pytest.fixture
def mock_entry_point(monkeypatch):
    def _mock_iter_entry_points(_, name):
        return {
            'dummy': [MockEntryPoint('dummy', 'who.cares')],
            'fake': [MockEntryPoint('fake', 'who.cares')],
            'multi': [MockEntryPoint('dummy', 'who.cares'), MockEntryPoint('fake', 'who.cares')],
            'unknown': []
        }[name]

    monkeypatch.setattr('flask_multiauth.util.iter_entry_points', _mock_iter_entry_points)


def test_resolve_provider_type_class():
    assert resolve_provider_type(DummyBase, Dummy) is Dummy
    with pytest.raises(TypeError):
        resolve_provider_type(DummyBase, FakeDummy)


@pytest.mark.usefixtures('mock_entry_point')
def test_resolve_provider_type_invalid():
    # unknown type
    with pytest.raises(ValueError):
        assert resolve_provider_type(DummyBase, 'unknown')
    # non-unique type
    with pytest.raises(RuntimeError):
        assert resolve_provider_type(DummyBase, 'multi')
    # invalid type
    with pytest.raises(TypeError):
        assert resolve_provider_type(DummyBase, 'fake')


@pytest.mark.usefixtures('mock_entry_point')
def test_resolve_provider_type():
    assert resolve_provider_type(DummyBase, 'dummy') is Dummy


@pytest.mark.parametrize(('valid', 'auth_providers', 'identity_providers', 'provider_map'), (
    (False, ['a'], [],    {}),
    (False, ['a'], ['a'], {}),
    (False, ['a'], ['b'], {}),
    (False, ['a'], ['b'], {'a': 'c'}),
    (True,  ['a'], ['b'], {'a': 'b'}),
    (True,  [],    ['b'], {'a': 'b'}),
))
def test_validate_provider_map(valid, auth_providers, identity_providers, provider_map):
    state = _MultiAuthState(None, None)
    state.auth_providers = {x: {} for x in auth_providers}
    state.identity_providers = {x: {} for x in identity_providers}
    state.provider_map = {a: [{'identity_provider': u}] for a, u in iteritems(provider_map)}
    if valid:
        validate_provider_map(state)
    else:
        pytest.raises(ValueError, validate_provider_map, state)


def test_classproperty():
    class Foo(object):
        @classproperty
        @classmethod
        def bar(cls):
            return 'foobar'

    class B(Foo):
        pass

    class C(Foo):
        pass

    assert Foo.bar == 'foobar'
    assert B.bar == 'foobar'
    assert C.bar == 'foobar'
    B.bar = 'moo'
    assert Foo.bar == 'foobar'
    assert B.bar == 'moo'
    assert C.bar == 'foobar'
    Foo.bar = 'asdf'
    assert Foo.bar == 'asdf'
    assert B.bar == 'moo'
    assert C.bar == 'asdf'
    inst = Foo()
    assert inst.bar == 'asdf'
    inst.bar = 'xyz'
    assert inst.bar == 'xyz'
    assert Foo.bar == 'asdf'


def test_supports_meta_no_support_attrs():
    @add_metaclass(SupportsMeta)
    class BrokenBase(object):
        pass

    with pytest.raises(AttributeError):
        class Test(BrokenBase):
            pass


@pytest.fixture(params=(True, False))
def supports_base(request):
    @add_metaclass(SupportsMeta)
    class Base(object):
        if request.param:
            __support_attrs__ = {SupportsMeta.callable(lambda cls: cls.has_foo, 'blah'): 'foo'}
        else:
            __support_attrs__ = {'has_foo': 'foo'}
        has_foo = False

        def foo(self):
            pass

    return Base


def test_supports_meta_ok(supports_base):
    # attr is false, method not overridden
    class Test(supports_base):
        pass

    # attr is true, method overridden
    class Test(supports_base):
        has_foo = True

        def foo(self):
            pass


def test_supports_meta_fail(supports_base):
    # attr is true, method not overridden
    with pytest.raises(TypeError):
        class Test(supports_base):
            has_foo = True

    # attr is false, method overridden
    with pytest.raises(TypeError):
        class Test(supports_base):
            def foo(self):
                pass


def test_supports_meta_inheritance(supports_base):
    class TestBase(supports_base):
        has_foo = True

        def foo(self):
            pass

    class Test(TestBase):
        pass

    with pytest.raises(TypeError):
        class Test(TestBase):
            has_foo = False


def test_supports_meta_multi():
    @add_metaclass(SupportsMeta)
    class Base(object):
        __support_attrs__ = {'has_foobar': ('foo', 'bar')}
        has_foobar = False

        def foo(self):
            pass

        def bar(self):
            pass

    # everything ok
    class Test(Base):
        pass

    # bar missing
    with pytest.raises(TypeError):
        class Test(supports_base):
            has_foobar = True

            def foo(self):
                pass


def test_supports_meta_default_true():
    @add_metaclass(SupportsMeta)
    class Base(object):
        __support_attrs__ = {'has_foo': 'foo'}
        has_foo = True

        def foo(self):
            pass

    # foo missing
    with pytest.raises(TypeError):
        class Test(Base):
            pass
