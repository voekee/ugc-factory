"""Run the actual launcher monitor with a virtual clock, without paid allocation."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize('became_ready, expect_timeout', [(True, False), (False, True)])
def test_monitor_deadline_applies_to_initial_startup_only(became_ready, expect_timeout):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is needed to execute launcher JavaScript')
    html = (Path(__file__).parents[1]/'launcher/onboarding.html').read_text()
    function = re.search(r'async function pollWorkspace\(\)\{[\s\S]*?\n\}\n\n\$\("#sessionModel"\)', html).group(0)
    function = function.rsplit('\n\n', 1)[0]
    code = '''const assert=require('node:assert/strict');
let calls=0, now=0, rendered=[];
Date.now=()=>now;
const setTimeout=cb=>{now+=3000; cb();};
let currentSessionToken='',currentWorkspaceUrl='';
const get=async()=>({active:++calls<=300, ready:READY && calls<=250});
const renderActiveSession=status=>rendered.push(status);
''' .replace('READY', json.dumps(became_ready)) + function + '''
(async()=>{
 let timedOut=false;
 try {await pollWorkspace();} catch(error) {
  assert.match(error.message,/did not become ready/);timedOut=true;
 }
 assert.equal(timedOut, EXPECT_TIMEOUT);
 if(!timedOut){assert.equal(calls,301); assert.equal(rendered.at(-1).active,false);}
 else assert.equal(calls,241);
})().catch(error=>{console.error(error);process.exitCode=1;});
''' .replace('EXPECT_TIMEOUT', json.dumps(expect_timeout))
    subprocess.run([node,'-e',code],check=True,capture_output=True,text=True,timeout=10)
