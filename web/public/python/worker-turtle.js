/* Python objects stay in the Worker; packets contain only bounded typed values. */
(function(root) {
    'use strict'
    var own = Function.prototype.call.bind(Object.prototype.hasOwnProperty)
    var NativePromise = root.Promise
    var nativeThen = Function.prototype.call.bind(NativePromise.prototype.then)
    var resolvePromise = NativePromise.resolve.bind(NativePromise)
    function then(promise,fulfilled,rejected){return nativeThen(resolvePromise(promise),fulfilled,rejected)}
    root.TeachingPythonWorkerTurtle = {
        create: function(sk,send,failure,startCallback,canRunCallback) {
            var pending=new Map(),callbacks=new Map(),callbackIds=new WeakMap(),references=new Map(),bindings=new WeakMap()
            var requestNumber=0,callbackNumber=0,module=null,schema=null
            var eventQueue=[],callbackActive=false,callbackFailed=false
            function request(packet) {
                packet.type='turtle-request';packet.requestId=++requestNumber
                return new NativePromise(function(resolve,reject){pending.set(packet.requestId,{resolve:resolve,reject:reject});send(packet)})
            }
            function suspend(promise) {
                var value
                var suspension=new sk.misceval.Suspension()
                suspension.resume=function(){if(suspension.data.error)throw suspension.data.error;return value}
                suspension.data={type:'Sk.promise',promise:then(promise,function(result){value=result;return result})}
                return suspension
            }
            function encode(value,depth) {
                if(depth>8)throw new sk.builtin.ValueError('绘图参数嵌套过深')
                if(value===undefined||value===null||value===sk.builtin.none.none$)return {kind:'none'}
                if(bindings.has(value))return bindings.get(value)
                if(value instanceof sk.builtin.func||value instanceof sk.builtin.method) {
                    var id=callbackIds.get(value)
                    if(!id){if(callbackNumber>=1024)throw new sk.builtin.ValueError('回调数量超出限制');id=++callbackNumber;callbackIds.set(value,id);callbacks.set(id,value)}
                    return {kind:'callback',callbackId:id}
                }
                if(value instanceof sk.builtin.bool)return {kind:'bool',value:!!value.v}
                if(value instanceof sk.builtin.str)return {kind:'str',value:value.v}
                if(value instanceof sk.builtin.int_)return {kind:'int',value:sk.builtin.asnum$(value)}
                if(value instanceof sk.builtin.float_)return {kind:'float',value:value.v}
                if(value instanceof sk.builtin.tuple||value instanceof sk.builtin.list)return {kind:value instanceof sk.builtin.tuple?'tuple':'list',items:value.v.map(function(item){return encode(item,depth+1)})}
                throw new sk.builtin.TypeError('不支持的绘图参数类型')
            }
            function RefToken(packet){this.packet=packet}
            function decode(packet) {
                if(!packet)throw new sk.builtin.RuntimeError('绘图响应无效')
                if(packet.kind==='none')return sk.builtin.none.none$
                if(packet.kind==='bool')return packet.value?sk.builtin.bool.true$:sk.builtin.bool.false$
                if(packet.kind==='str')return new sk.builtin.str(packet.value)
                if(packet.kind==='int')return new sk.builtin.int_(packet.value)
                if(packet.kind==='float')return new sk.builtin.float_(packet.value)
                if(packet.kind==='tuple'||packet.kind==='list')return new sk.builtin[packet.kind](packet.items.map(decode))
                if(packet.kind==='ref') {
                    if(!references.has(packet.objectId))sk.misceval.callsimArray(module[packet.scope],[new RefToken(packet)])
                    return references.get(packet.objectId)
                }
                throw new sk.builtin.RuntimeError('绘图返回类型无效')
            }
            function buildMethod(scope,name,meta) {
                var fn=function() {
                    var args=Array.prototype.slice.call(arguments),object=null
                    if(scope!=='module'){object=bindings.get(args.shift());if(!object)throw new sk.builtin.RuntimeError('海龟对象已失效')}
                    if(args.length<meta.min || args.length>meta.max)throw new sk.builtin.TypeError(name.replace(/_\$[a-z]+\$$/i,'')+'() takes '+(meta.min===meta.max?'exactly '+meta.max:'between '+meta.min+' and '+meta.max)+' positional argument(s) ('+args.length+' given)')
                    var packet={op:'call',scope:scope,method:name,args:args.map(function(arg){return encode(arg,0)})}
                    if(object)packet.objectId=object.objectId
                    return suspend(then(request(packet),function(reply){return decode(reply.value)}))
                }
                fn.co_name=new sk.builtin.str(name.replace(/_\$[a-z]+\$$/i,''));fn.co_varnames=meta.args.slice();fn.$defaults=[]
                for(var i=meta.min;i<meta.args.length;i++)fn.$defaults.push(sk.builtin.none.none$)
                if(scope!=='module')fn.co_varnames.unshift('self')
                return new sk.builtin.func(fn)
            }
            function buildClass(kind) {
                return sk.misceval.buildClass(module,function(globals,locals){
                    var init=function(self,shape) {
                        if(shape instanceof RefToken){bindings.set(self,shape.packet);references.set(shape.packet.objectId,self);return sk.builtin.none.none$}
                        var args=kind==='Turtle'?[encode(shape===undefined?new sk.builtin.str('classic'):shape,0)]:[]
                        return suspend(then(request({op:'create',scope:kind,args:args}),function(reply){bindings.set(self,reply.value);references.set(reply.value.objectId,self);return sk.builtin.none.none$}))
                    }
                    if(kind==='Turtle'){init.co_varnames=['self','shape'];init.$defaults=[sk.builtin.none.none$,new sk.builtin.str('classic')];init.co_argcount=2}
                    locals.__init__=new sk.builtin.func(init)
                    Object.keys(schema[kind]).forEach(function(name){locals[name]=buildMethod(kind,name,schema[kind][name])})
                },kind,[])
            }
            function builtinModule() {
                return suspend(then(request({op:'init'}),function(reply){
                    schema=reply.schema;module={__name__:new sk.builtin.str('turtle')}
                    Object.keys(schema.module).forEach(function(name){module[name]=buildMethod('module',name,schema.module[name])})
                    module.Turtle=buildClass('Turtle');module.Screen=buildClass('Screen')
                    return module
                }))
            }
            // The global factory has no port property and exposes only the fixed turtle module.
            root.TeachingPythonTurtleModule=builtinModule
            function pumpCallbacks() {
                if(callbackActive || callbackFailed || !eventQueue.length || (canRunCallback && !canRunCallback()))return
                var event=eventQueue.shift(),callback=callbacks.get(event.callbackId)
                if(!callback){pumpCallbacks();return}
                callbackActive=true
                var finish=startCallback()||function(){}
                try {
                    then(sk.misceval.applyAsync(undefined,callback,undefined,undefined,undefined,event.args.map(decode)),function(){
                        finish();callbackActive=false;pumpCallbacks()
                    },function(error){callbackFailed=true;eventQueue=[];failure(error)})
                }catch(error){callbackFailed=true;eventQueue=[];failure(error)}
            }
            function receive(packet) {
                if(packet.type==='turtle-result') {
                    var waiting=pending.get(packet.requestId);if(!waiting)return true;pending.delete(packet.requestId)
                    if(packet.error){var Exception=sk.builtin[packet.error.name];waiting.reject(new (typeof Exception==='function'?Exception:sk.builtin.RuntimeError)(packet.error.message))}
                    else waiting.resolve(packet)
                    return true
                }
                if(packet.type==='turtle-event') {
                    if(callbacks.has(packet.callbackId)){
                        if(eventQueue.length>=32){callbackFailed=true;eventQueue=[];failure(new sk.builtin.ValueError('绘图事件队列超过32项，请减少重复事件'));return true}
                        eventQueue.push(packet);pumpCallbacks()
                    }
                    return true
                }
                return false
            }
            return {receive:receive,resumeCallbacks:pumpCallbacks,source:'var $builtinmodule = function () { return TeachingPythonTurtleModule(); };'}
        }
    }
}(self))
