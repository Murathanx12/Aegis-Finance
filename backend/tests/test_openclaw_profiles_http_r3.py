"""Source-selected HTTP/profile fixtures only: no backend/env/network/native."""
import ast,json,re,subprocess,threading,time
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any,Callable
import pytest

SERVICES=Path(__file__).parents[1]/'services'
def selected(path,names,scope):
    tree=ast.parse(path.read_bytes());nodes=[]
    for n in tree.body:
        if isinstance(n,(ast.FunctionDef,ast.ClassDef)) and n.name in names:nodes.append(n)
        elif isinstance(n,(ast.Assign,ast.AnnAssign)):
            targets=n.targets if isinstance(n,ast.Assign) else [n.target]
            if any(isinstance(t,ast.Name) and t.id in names for t in targets):nodes.append(n)
    nodes.insert(0,ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0))
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec',dont_inherit=True),scope)
    return scope

def http():
    return selected(SERVICES/'openclaw_http.py',{'HTTP_VERBS','_VALUE_FLAGS','_BOOL_FLAGS','_WRAP_START','_WRAP_END','RETRY_ON_RESET',
        'parse_argv','tool_args','render','unwrap','HttpTransport','is_reset','base_url','navigate_timeout_ms'},
        dict(json=json,re=re,subprocess=subprocess,Any=Any,Callable=Callable,_config=NS()))

def client(transport):
    ns=dict(json=json,re=re,subprocess=subprocess,time=time,os=NS(environ={}),_config=NS(OPENCLAW_BROWSER_TRANSPORT='cli',OPENCLAW_BROWSER_TRANSPORT_DEDICATED='http'),
        _VALUE_FLAGS=frozenset({'--browser-profile','--target-id','--fn','--format','--time','--limit'}),TRANSPORT_ENV='AEGIS_OPENCLAW_TRANSPORT',TRANSPORTS=('cli','http'),
        dedicated_profiles=lambda:('muratclaw',),profile=lambda name=None:name or 'muratclaw',_http=lambda:transport,
        _ledger_add=lambda *a:None,invalidate_profile_cache=lambda *a:None,_LEDGER_LOCK=threading.Lock(),_CLI_LEDGER={'timeouts':0},
        _resolve_cli=lambda:(_ for _ in ()).throw(AssertionError('CLI_FALLBACK')), _strip=lambda x:(x or '').strip(),
        _PROFILE_CACHE={},OPENCLAW_PROFILE_ASSERT_TTL_S=60,_clock=lambda:0,_bump=lambda *a:None,
        OpenClawRefused=ValueError,is_operator_profile=lambda name:True)
    selected(SERVICES/'openclaw_client.py',{'_cmd_key','_profile_of','browser_transport','_run_http','_run_unleased','profiles','assert_profile'},ns)
    ns['_run']=ns['_run_unleased'];return ns

class Session:
    def __init__(self,payload,status=200):self.payload=payload;self.status=status;self.calls=[]
    def post(self,url,**kw):
        self.calls.append((url,kw))
        return NS(status_code=self.status,json=lambda:self.payload)

def transport(rows=None,payload=None):
    module=http();rows=[{'name':'muratclaw','running':True,'tabCount':2,'isDefault':True}] if rows is None else rows
    session=Session(payload if payload is not None else {'ok':True,'result':{'details':{'profiles':rows},'content':[]}})
    value=module['HttpTransport'](session=session,token_fn=lambda:'FIXTURE_TOKEN',url='http://fixture.invalid')
    value._port_open=lambda:False
    return module,value,session

def test_real_http_profiles_to_unchanged_parser_and_cache_without_cli():
    h,t,session=transport();c=client(t)
    assert c['assert_profile'](name='muratclaw')['state']=='running'
    assert c['assert_profile'](name='muratclaw')['cached'] is True
    assert len(session.calls)==1 and session.calls[0][1]['json']=={'tool':'browser','args':{'action':'profiles'}}
    assert c['profiles'].__code__.co_argcount==0

def test_zero_argument_fake_profiles_remains_compatible():
    h,t,s=transport();c=client(t);c['profiles']=lambda:[{'name':'muratclaw','state':'running','tag':''}]
    assert c['assert_profile'](name='muratclaw')['ok'] is True
    assert s.calls==[]

@pytest.mark.parametrize('rows',[None,{},[{}],[{'name':'muratclaw','running':'true'}],[{'name':'other\nmuratclaw: running','running':True}],
    [{'name':'muratclaw','running':True},{'name':'muratclaw','running':False}],[{'name':'muratclaw','running':True,'tabCount':True}],
    [{'name':'muratclaw','running':True,'isDefault':'true'}]])
def test_malformed_profile_listing_never_proves_profile_or_falls_to_cli(rows):
    payload={'ok':True,'result':{'details':{'profiles':rows}}};h,t,s=transport(payload=payload);c=client(t)
    with pytest.raises(ValueError,match='HTTP_PROFILES'):c['assert_profile'](name='muratclaw')

@pytest.mark.parametrize('body',[{'details':{'profiles':[],'truncated':True}},
    {'details':{'profiles':[{'name':'muratclaw','running':True}]},'content':[{'type':'text','text':'[truncated private fixture]'}]}])
def test_truncated_profile_listing_refuses_no_cli_fallback(body):
    h,t,s=transport(payload={'ok':True,'result':body});c=client(t)
    with pytest.raises(ValueError,match='HTTP_PROFILES_TRUNCATED'):c['assert_profile'](name='muratclaw')

@pytest.mark.parametrize('reply',[{'ok':False,'error':{'message':'FIXTURE_FAILURE'}},{'not_ok':True}])
def test_http_failure_proves_no_profile_no_cli(reply):
    h,t,s=transport(payload=reply);c=client(t)
    with pytest.raises(ValueError,match='REFUSED_BROWSER_PROFILE_UNAVAILABLE'):c['assert_profile'](name='muratclaw')

@pytest.mark.parametrize('result',[None,NS(http_truncated=True,args=['browser','profiles'],returncode=0,stdout='muratclaw: running',stderr='')])
def test_served_transport_none_or_truncation_cannot_trigger_large_cli(result):
    t=NS(serves=lambda a:True,run=lambda *a,**k:result);c=client(t)
    r=c['_run_unleased'](['browser','profiles'])
    assert r.returncode==1 and not r.stdout

def test_empty_or_stopped_profiles_refuse_authentication_and_no_fabrication():
    for rows in ([],[{'name':'muratclaw','running':False}]):
        h,t,s=transport(rows=rows);c=client(t)
        with pytest.raises(ValueError,match='REFUSED_BROWSER_PROFILE_UNAVAILABLE'):c['assert_profile'](name='muratclaw')

def test_only_supported_profiles_args_are_mapped_unrelated_fallback_unchanged():
    h,t,s=transport()
    assert t.serves(['browser','profiles'])
    for args in (['browser','profiles','arbitrary'],['browser','profiles','--max-chars','10'],['browser','profiles','--unknown'],['browser','start']):
        assert not t.serves(args) and t.run(args) is None
    assert h['tool_args'](h['parse_argv'](['browser','--browser-profile','muratclaw','profiles','--json']))=={'profile':'muratclaw','action':'profiles'}

def test_profiles_missing_structured_details_does_not_parse_private_text_as_proof():
    h,t,s=transport(payload={'ok':True,'result':{'content':[{'type':'text','text':'muratclaw: running PRIVATE_FIELD'}]}})
    with pytest.raises(ValueError,match='HTTP_PROFILES_SHAPE'):client(t)['assert_profile'](name='muratclaw')

def test_profiles_count_and_rendered_output_caps():
    h=http()
    with pytest.raises(ValueError,match='SHAPE'):h['render']('profiles',{'details':{'profiles':[{}]*129}})
    rows=[{'name':str(i)+'x'*125,'running':True,'tabCount':1000000,'isDefault':True} for i in range(128)]
    with pytest.raises(ValueError,match='OUTPUT_BOUND'):h['render']('profiles',{'details':{'profiles':rows}})

def test_timeout_retains_original_timeout_class_and_never_uses_cli():
    h,t,s=transport()
    def timeout(*a,**k):raise TimeoutError('FIXTURE_TOKEN_PRIVATE')
    s.post=timeout
    with pytest.raises(subprocess.TimeoutExpired):client(t)['assert_profile'](name='muratclaw')

def test_http_error_fixture_token_is_redacted_and_no_profile_proven():
    h,t,s=transport(payload={'ok':False,'error':{'message':'private FIXTURE_TOKEN'}})
    result=t.run(['browser','profiles'])
    assert result.returncode==1 and result.stdout=='' and 'FIXTURE_TOKEN' not in result.stderr

def test_default_cli_policy_still_honored_explicitly():
    h,t,s=transport();c=client(t);c['_config'].OPENCLAW_BROWSER_TRANSPORT_DEDICATED='cli'
    with pytest.raises(AssertionError,match='CLI_FALLBACK'):c['profiles']()
    assert s.calls==[]

def test_profiles_parser_keeps_original_port_tags_and_tab_metadata():
    rows=[{'name':'muratclaw','running':True,'tabCount':2,'isDefault':True,'cdpPort':18802,'driver':'openclaw'},
          {'name':'other','running':False,'isRemote':True,'driver':'existing-session','cdpPort':0}]
    h,t,s=transport(rows=rows);parsed=client(t)['profiles']()
    assert parsed==[{'name':'muratclaw','state':'running','tag':'default','tabs':2,'port':18802},
                    {'name':'other','state':'stopped','tag':'remote','port':0}]


def test_main_broker_namespace_isolation_preserved_for_future_suffixes():
    ns=dict(re=re,os=NS(environ={}))
    selected(SERVICES/'openclaw_client.py',{'_BROKER_CLI_NAME','_broker_free_cli_environment'},ns)
    private_names=('PC-PAPER_KEY','PC_PAPER_FUTURE_SUFFIX','ALPACA_UNLISTED_SUFFIX','APCA_NEW_VARIABLE','AAT_HACK_DIAGNOSTIC')
    env={name:'fixture-private-value' for name in private_names}
    env.update(FRED_API_KEY='fixture-research',OPENCLAW_NODE_BIN='fixture-node')
    clean=ns['_broker_free_cli_environment'](env)
    assert not set(private_names)&set(clean)
    assert clean['FRED_API_KEY']=='fixture-research' and clean['OPENCLAW_NODE_BIN']=='fixture-node'
    assert clean['AEGIS_IGNORE_DOTENV']=='1'
    # The installed suffix-only predecessor would miss the future aliases.
    weaker=re.compile(r'^(?:(?:PC[-_]PAPER)[-_](?:KEY|SECRET)$|(?:ALPACA|APCA|AAT_HACK).*?(?:SECRET|KEY_ID|API_KEY|TOKEN))',re.I)
    assert weaker.search('APCA_NEW_VARIABLE') is None
