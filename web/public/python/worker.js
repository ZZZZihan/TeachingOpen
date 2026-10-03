/* The sole computation realm. The host terminates this Worker before acknowledging stop. */
(function(root) {
    'use strict'
    var CHANNEL='teaching-python-v1',MAX_CODE=256000,MAX_OUTPUT=20000,MAX_TEXT=2048,MAX_INPUT=4096
    var NativePromise=root.Promise,nativeThen=Function.prototype.call.bind(NativePromise.prototype.then),resolvePromise=NativePromise.resolve.bind(NativePromise),NativeDate=root.Date
    function then(promise,fulfilled,rejected){return nativeThen(resolvePromise(promise),fulfilled,rejected)}
    var stringify=root.String,now=root.Date.now.bind(root.Date),schedule=root.setTimeout.bind(root),cancelTimer=root.clearTimeout.bind(root)
    var own=Function.prototype.call.bind(Object.prototype.hasOwnProperty),addListener=root.addEventListener.bind(root),removeListener=root.removeEventListener.bind(root)
    var started=false
    function bootstrap(event) {
        var data=event.data
        if(started||!data||data.channel!==CHANNEL||data.type!=='run'||typeof data.runId!=='string'||!/^[a-f0-9]{32}$/.test(data.runId)||typeof data.code!=='string'||data.code.length>MAX_CODE||event.ports.length!==1)return
        started=true;removeListener('message',bootstrap)
        var runId=data.runId,code=data.code,port=event.ports[0],post=port.postMessage.bind(port)
        var pendingInput=null,requestNumber=0,callbackNumber=0,output='',outputUnits=0,truncated=false,flushTimer=null,mainFinished=false,mainStarted=false,sk,bridge,startProgram
        data=null;event=null
        function send(type,text,requestId){post({channel:CHANNEL,type:type,runId:runId,text:text,prompt:type==='input'?text:undefined,requestId:requestId})}
        function sendTurtle(packet){packet.channel=CHANNEL;packet.runId=runId;post(packet)}
        function flush(){if(flushTimer)cancelTimer(flushTimer);flushTimer=null;while(output.length){var length=Math.min(MAX_TEXT,output.length);if(length<output.length&&/[\uD800-\uDBFF]/.test(output.charAt(length-1))&&/[\uDC00-\uDFFF]/.test(output.charAt(length)))length--;send('output',output.slice(0,length));output=output.slice(length)}}
        function write(value){if(truncated)return;var text=stringify(value),length=Math.min(MAX_OUTPUT+1-outputUnits,text.length);if(length<text.length&&/[\uD800-\uDBFF]/.test(text.charAt(length-1))&&/[\uDC00-\uDFFF]/.test(text.charAt(length)))length--;output+=text.slice(0,length);outputUnits+=length;if(outputUnits>=MAX_OUTPUT+1||length<text.length)truncated=true;if(truncated&&outputUnits<=MAX_OUTPUT){output+='\n';outputUnits++}if(!flushTimer)flushTimer=schedule(flush,20)}
        function failure(error){flush();send('error',stringify(error).slice(0,MAX_TEXT))}
        function input(prompt){flush();return new NativePromise(function(resolve,reject){if(pendingInput){reject(new Error('上一次输入尚未结束'));return}var requestId=stringify(++requestNumber);pendingInput={requestId:requestId,resolve:resolve,reject:reject,started:now()};send('input',stringify(prompt||'').slice(0,MAX_TEXT),requestId)})}
        port.onmessage=function(messageEvent){var reply=messageEvent.data;if(!reply||reply.channel!==CHANNEL||reply.runId!==runId)return
            if(reply.type==='start'&&startProgram&&!mainStarted){mainStarted=true;schedule(startProgram,0);return}
            if(bridge&&bridge.receive(reply))return
            if(reply.type!=='input-result'||!pendingInput||reply.requestId!==pendingInput.requestId||typeof reply.value!=='string'||reply.value.length>MAX_INPUT)return
            var waiting=pendingInput;pendingInput=null;if(sk.execStart)sk.execStart=new NativeDate(+sk.execStart+Math.max(0,now()-waiting.started));send('resumed',undefined,waiting.requestId);waiting.resolve(reply.value);if(bridge)bridge.resumeCallbacks()
        }
        port.start()
        schedule(function(){try{
            sk=root.TeachingPythonRuntime()
        // The single host-owned Worker is the only computation realm for this run.
        ;['Worker','SharedWorker','importScripts'].forEach(function(name){try{Object.defineProperty(root,name,{value:undefined,writable:false,configurable:false})}catch(ignore){root[name]=undefined}})
            bridge=root.TeachingPythonWorkerTurtle.create(sk,sendTurtle,failure,function(){
                var callbackId=stringify(++callbackNumber)
                if(mainFinished)sk.execStart=new NativeDate()
                send('callback-start',undefined,callbackId)
                return function(){flush();send('callback-done',undefined,callbackId)}
            },function(){return !pendingInput})
            delete root.TeachingPythonWorkerTurtle
            sk.configure({output:write,read:function(path){if(path==='src/lib/turtle.js')return bridge.source;if(!sk.builtinFiles||!own(sk.builtinFiles.files,path))throw new Error("File not found: '"+path+"'");return sk.builtinFiles.files[path]},__future__:sk.python2,execLimit:30000,yieldLimit:100,inputfun:input,inputfunTakesPrompt:true,timeoutMsg:function(){return '运行时间较长，请简化程序后重试。'},uncaughtException:failure})
            startProgram=function(){try{var result=sk.misceval.asyncToPromise(function(){return sk.importMainWithBody('<stdin>',false,code,true)});code=null;then(result,function(){mainFinished=true;flush();send('done')},failure)}catch(error){failure(error)}}
            send('ready')
        }catch(error){failure(error)}},0)
    }
    addListener('message',bootstrap)
}(self))
