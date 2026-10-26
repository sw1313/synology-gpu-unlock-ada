#!/usr/bin/python3
# SPDX-License-Identifier: GPL-2.0-only
"""Run the verified single-card transaction before DSM's udev coldplug.
Failure never prevents global udev startup. A started GPU transaction keeps
its target driver_override hold until all kernel-side gates pass.
"""
import datetime, fcntl, hashlib, json, os, subprocess, sys
from pathlib import Path

ROOT=Path('/usr/local/share/gpu-unlock-ada')
CONF=Path('/etc/gpu-unlock-ada/mode.json')
RUN=Path('/run/gpu-unlock-ada')
HOLD='gpu-unlock-ada-hold'
log = None

def say(message):
    line=datetime.datetime.now().isoformat()+' gpu-unlock-ada: '+message
    print(line,flush=True)
    log.write(line+'\n')

def atomic_json(path,value):
    temp=path.with_name(path.name+'.tmp')
    with temp.open('w') as f:json.dump(value,f,indent=2);f.write('\n')
    os.chmod(str(temp),0o600)
    os.replace(str(temp),str(path))

def cmd(args):
    p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    if p.stdout.strip():say(p.stdout.strip())
    if p.returncode:raise RuntimeError('command failed (%s): %s'%(p.returncode,' '.join(args)))

def perform():
    # Keep the same lock across all boot gates, including early returns.
    with (RUN/'lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        perform_locked()

def perform_locked():
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    state={'boot_id':boot,'time':datetime.datetime.now().isoformat(),'status':'starting','gpu_held':False}
    if (RUN/'success').exists():
        say('already completed successfully in this boot');return
    if not CONF.exists():say('no config: stock boot');return
    cfg=json.loads(CONF.read_text())
    if cfg.get('mode') not in ('once','persistent'):
        say('disabled: stock boot');return
    target=cfg['target'];dev=Path('/sys/bus/pci/devices')/target
    state['target']=target
    try:
        if target!='0000:01:00.0':raise RuntimeError('only the reviewed single exact PCI target is admitted')
        for option in ('-r','-v'):
            expected=cfg['kernel_release' if option=='-r' else 'kernel_version']
            actual=subprocess.check_output(['/bin/uname',option],text=True).strip()
            if actual!=expected:raise RuntimeError('kernel identity changed: '+actual)
        for key in ('vendor','device','subsystem_vendor','subsystem_device'):
            if (dev/key).read_text().strip()!=cfg[key]:raise RuntimeError('PCI identity mismatch: '+key)
        if (dev/'driver').exists():
            state['status']='too_late_stock_driver_already_bound'
            say('target already bound; no GPU transaction attempted')
            return
        old=(dev/'driver_override').read_text().strip()
        if old not in ('','(null)'):raise RuntimeError('foreign PCI driver_override: '+old)
        for relative,digest in json.loads((ROOT/'manifest.json').read_text()).items():
            p=ROOT/relative
            if hashlib.sha256(p.read_bytes()).hexdigest()!=digest:raise RuntimeError('payload checksum mismatch: '+relative)
        if cfg['mode']=='once':
            cfg['mode']='disabled'
            cfg['one_shot_consumed_boot']=boot
            atomic_json(CONF,cfg)
        for module in ('libsha256','fbdev','fb'):
            if not (Path('/sys/module')/module).exists():
                cmd(['/sbin/insmod',str(ROOT/'modules'/(module+'.ko'))])
        if Path('/sys/module/gpu_unlock').exists():raise RuntimeError('gpu_unlock was already loaded unexpectedly')
        (dev/'driver_override').write_text(HOLD+'\n')
        state['gpu_held']=True;state['status']='transaction_in_progress'
        atomic_json(RUN/'state.json',state)
        say('begin: '+target+' is unbound and held before udev/NVIDIA')
        cmd(['/sbin/insmod',str(ROOT/'modules/gpu_unlock.ko'),'targets='+target,'ad106_experimental=1'])
        params=Path('/sys/module/gpu_unlock/parameters')
        result=(params/'transaction_result').read_text().strip()
        state['transaction_result']=result
        if result!='0':raise RuntimeError('kernel transaction did not pass all gates: '+result)
        if (params/'targets').read_text().strip()!=target:raise RuntimeError('loaded target mismatch')
        if (params/'ad106_experimental').read_text().strip() not in ('Y','1'):raise RuntimeError('AD106 opt-in mismatch')
        if (dev/'driver').exists():raise RuntimeError('unexpected driver bound while GPU was held')
        (dev/'driver_override').write_text('\n')
        state['gpu_held']=False;state['status']='unlocked_verified'
        (RUN/'success').write_text(boot+'\n')
        say('PASS: complete transaction result=0; released PCI hold for stock NVIDIA')
    except Exception as error:
        state['status']='blocked_after_transaction' if state['gpu_held'] else 'precheck_failed_stock_boot'
        state['error']=str(error)
        say('FAIL: '+str(error))
        if state['gpu_held']:say('PCI hold remains; do not force-unload. A full power-off may be required.')
    finally:
        atomic_json(RUN/'state.json',state)
        atomic_json(Path('/etc/gpu-unlock-ada/last-result.json'),state)

def main():
    global log
    RUN.mkdir(mode=0o700, exist_ok=True)
    log = open('/var/log/gpu-unlock-ada.log', 'a', buffering=1)
    try:
        perform()
    except Exception as error:
        say('startup-wrapper error: '+repr(error))
    finally:
        log.close()
    # The systemd drop-in also ignores failure: global coldplug must continue.
    return 0

if __name__ == '__main__':
    sys.exit(main())
