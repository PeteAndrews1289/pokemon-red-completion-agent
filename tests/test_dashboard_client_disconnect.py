from http import HTTPStatus
from types import SimpleNamespace

import pytest

from pokemon_red_completion.progress_dashboard import _DashboardRequestHandler


def response_handler(*, fail_stage=None, error=None):
    handler=object.__new__(_DashboardRequestHandler)
    handler.close_connection=False
    calls=[]
    def record(stage,*values):
        if fail_stage==stage:raise error
        calls.append((stage,*values))
    handler.send_response=lambda value:record('status',value)
    handler.send_header=lambda key,value:record('header',key,value)
    handler.end_headers=lambda:record('flush')
    handler.wfile=SimpleNamespace(write=lambda value:record('body',value))
    return handler,calls


@pytest.mark.parametrize('etag',[None,'"status-4"'])
def test_successful_observer_response_retains_payload_headers_and_etag(etag):
    handler,calls=response_handler()
    assert handler._send(HTTPStatus.OK,'application/json',b'{"view_only":true}',etag=etag) is None
    assert calls[0]==('status',HTTPStatus.OK) and calls[-1]==('body',b'{"view_only":true}')
    headers={key:value for kind,*args in calls if kind=='header' for key,value in [args]}
    assert headers['Content-Type']=='application/json'
    assert headers['Content-Length']==str(len(b'{"view_only":true}'))
    assert headers['Cache-Control']=='no-store' and headers['X-Frame-Options']=='DENY'
    assert ('ETag' in headers)==(etag is not None)
    if etag is not None:assert headers['ETag']==etag
    assert handler.close_connection is False


@pytest.mark.parametrize('stage',['status','header','flush','body'])
@pytest.mark.parametrize('error',[BrokenPipeError(32,'client disconnected'),ConnectionResetError(104,'client reset')])
def test_departed_read_only_client_closes_only_its_connection(stage,error):
    handler,calls=response_handler(fail_stage=stage,error=error)
    assert handler._send(HTTPStatus.OK,'application/json',b'{}') is None
    assert handler.close_connection is True
    assert not any(row[0]=='body' for row in calls)


@pytest.mark.parametrize('error',[OSError(5,'unexpected I/O failure'),RuntimeError('renderer defect'),TypeError('invalid response')])
def test_unexpected_response_errors_are_not_hidden(error):
    handler,_=response_handler(fail_stage='body',error=error)
    with pytest.raises(type(error)) as caught:
        handler._send(HTTPStatus.OK,'application/json',b'{}')
    assert caught.value is error
    assert handler.close_connection is False
