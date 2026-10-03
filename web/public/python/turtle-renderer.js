/* Only this fixed renderer runs in the opaque window. No student source is evaluated here. */
(function (root) {
    'use strict'
    var NativePromise = root.Promise
    var nativeThen = Function.prototype.call.bind(NativePromise.prototype.then)
    var resolvePromise = NativePromise.resolve.bind(NativePromise)
    function then(promise,fulfilled,rejected){return nativeThen(resolvePromise(promise),fulfilled,rejected)}
    var own = Function.prototype.call.bind(Object.prototype.hasOwnProperty)
    var SCHEMA = {
  "module": {
    "degrees": {
      "args": [
        "fullcircle"
      ],
      "max": 1,
      "min": 0
    },
    "radians": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pos": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "position": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "towards": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "distance": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "heading": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "xcor": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "ycor": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "fd": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "forward": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "undo": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "undobufferentries": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "setundobuffer": {
      "args": [
        "size"
      ],
      "max": 1,
      "min": 1
    },
    "bk": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "back": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "backward": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "setposition": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "setpos": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "goto_$rw$": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "setx": {
      "args": [
        "x"
      ],
      "max": 1,
      "min": 1
    },
    "sety": {
      "args": [
        "y"
      ],
      "max": 1,
      "min": 1
    },
    "home": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "rt": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "right": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "lt": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "left": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "seth": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "setheading": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "circle": {
      "args": [
        "radius",
        "extent",
        "steps"
      ],
      "max": 3,
      "min": 1
    },
    "pu": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "up": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "penup": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pd": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "down": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pendown": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "isdown": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "speed": {
      "args": [
        "speed"
      ],
      "max": 1,
      "min": 0
    },
    "pencolor": {
      "args": [
        "r",
        "g",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "fillcolor": {
      "args": [
        "r",
        "g",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "color": {
      "args": [
        "color",
        "fill",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "fill": {
      "args": [
        "flag"
      ],
      "max": 1,
      "min": 0
    },
    "begin_fill": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "end_fill": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "stamp": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "dot": {
      "args": [
        "size",
        "color",
        "g",
        "b",
        "a"
      ],
      "max": 5,
      "min": 0
    },
    "write": {
      "args": [
        "message",
        "move",
        "align",
        "font"
      ],
      "max": 4,
      "min": 1
    },
    "width": {
      "args": [
        "width"
      ],
      "max": 1,
      "min": 0
    },
    "pensize": {
      "args": [
        "width"
      ],
      "max": 1,
      "min": 0
    },
    "st": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "showturtle": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "ht": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "hideturtle": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "isvisible": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "shape": {
      "args": [
        "name"
      ],
      "max": 1,
      "min": 0
    },
    "colormode": {
      "args": [
        "cmode"
      ],
      "max": 1,
      "min": 0
    },
    "window_width": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "window_height": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "tracer": {
      "args": [
        "frames",
        "delay"
      ],
      "max": 2,
      "min": 0
    },
    "update": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "delay": {
      "args": [
        "delay"
      ],
      "max": 1,
      "min": 0
    },
    "reset": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "done": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "mainloop": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "clear": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "onclick": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "onrelease": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "ondrag": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "getscreen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "clone": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "getpen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "getturtle": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "bye": {
      "args": [],
      "max": 0,
      "min": 0
    }
  },
  "Turtle": {
    "degrees": {
      "args": [
        "fullcircle"
      ],
      "max": 1,
      "min": 0
    },
    "radians": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pos": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "position": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "towards": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "distance": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "heading": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "xcor": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "ycor": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "fd": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "forward": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "undo": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "undobufferentries": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "setundobuffer": {
      "args": [
        "size"
      ],
      "max": 1,
      "min": 1
    },
    "bk": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "back": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "backward": {
      "args": [
        "distance"
      ],
      "max": 1,
      "min": 1
    },
    "setposition": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "setpos": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "goto_$rw$": {
      "args": [
        "x",
        "y"
      ],
      "max": 2,
      "min": 1
    },
    "setx": {
      "args": [
        "x"
      ],
      "max": 1,
      "min": 1
    },
    "sety": {
      "args": [
        "y"
      ],
      "max": 1,
      "min": 1
    },
    "home": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "rt": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "right": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "lt": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "left": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "seth": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "setheading": {
      "args": [
        "angle"
      ],
      "max": 1,
      "min": 1
    },
    "circle": {
      "args": [
        "radius",
        "extent",
        "steps"
      ],
      "max": 3,
      "min": 1
    },
    "pu": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "up": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "penup": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pd": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "down": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "pendown": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "isdown": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "speed": {
      "args": [
        "speed"
      ],
      "max": 1,
      "min": 0
    },
    "pencolor": {
      "args": [
        "r",
        "g",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "fillcolor": {
      "args": [
        "r",
        "g",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "color": {
      "args": [
        "color",
        "fill",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "fill": {
      "args": [
        "flag"
      ],
      "max": 1,
      "min": 0
    },
    "begin_fill": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "end_fill": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "stamp": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "dot": {
      "args": [
        "size",
        "color",
        "g",
        "b",
        "a"
      ],
      "max": 5,
      "min": 0
    },
    "write": {
      "args": [
        "message",
        "move",
        "align",
        "font"
      ],
      "max": 4,
      "min": 1
    },
    "width": {
      "args": [
        "width"
      ],
      "max": 1,
      "min": 0
    },
    "pensize": {
      "args": [
        "width"
      ],
      "max": 1,
      "min": 0
    },
    "st": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "showturtle": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "ht": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "hideturtle": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "isvisible": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "shape": {
      "args": [
        "name"
      ],
      "max": 1,
      "min": 0
    },
    "colormode": {
      "args": [
        "cmode"
      ],
      "max": 1,
      "min": 0
    },
    "window_width": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "window_height": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "tracer": {
      "args": [
        "n",
        "delay"
      ],
      "max": 2,
      "min": 0
    },
    "update": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "delay": {
      "args": [
        "delay"
      ],
      "max": 1,
      "min": 0
    },
    "reset": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "done": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "mainloop": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "clear": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "onclick": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "onrelease": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "ondrag": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "getscreen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "clone": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "getpen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "getturtle": {
      "args": [],
      "max": 0,
      "min": 0
    }
  },
  "Screen": {
    "setup": {
      "args": [
        "width",
        "height",
        "startx",
        "starty"
      ],
      "max": 4,
      "min": 0
    },
    "addshape": {
      "args": [],
      "max": 2,
      "min": 1
    },
    "register_shape": {
      "args": [],
      "max": 2,
      "min": 1
    },
    "getshapes": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "tracer": {
      "args": [
        "frames",
        "delay"
      ],
      "max": 2,
      "min": 0
    },
    "delay": {
      "args": [
        "delay"
      ],
      "max": 1,
      "min": 0
    },
    "setworldcoordinates": {
      "args": [
        "llx",
        "lly",
        "urx",
        "ury"
      ],
      "max": 4,
      "min": 4
    },
    "clearscreen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "clear": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "update": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "resetscreen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "reset": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "window_width": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "window_height": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "turtles": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "bgpic": {
      "args": [
        "name"
      ],
      "max": 1,
      "min": 0
    },
    "bgcolor": {
      "args": [
        "color",
        "g",
        "b",
        "a"
      ],
      "max": 4,
      "min": 0
    },
    "done": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "mainloop": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "bye": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "exitonclick": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "onclick": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "listen": {
      "args": [],
      "max": 0,
      "min": 0
    },
    "onkey": {
      "args": [
        "method",
        "keyValue"
      ],
      "max": 2,
      "min": 2
    },
    "onscreenclick": {
      "args": [
        "method",
        "btn",
        "add"
      ],
      "max": 3,
      "min": 1
    },
    "ontimer": {
      "args": [
        "method",
        "interval"
      ],
      "max": 2,
      "min": 0
    }
  }
}
    root.TeachingPythonTurtleRenderer = {
        create: function (sk, target, emit) {
            var disposed = false
            var module = null
            var objects = new Map()
            var ids = new WeakMap()
            var callbacks = new Map()
            var nextId = 0
            var total = 0
            var pending = 0
            var ready = null
            var graphicsSent = false
            var queuedFrames = 0
            var measureContext = null
            function error(message) { throw new sk.builtin.ValueError(message) }
            function initialise() {
                if (!ready) {
                    sk.configure({ __future__: sk.python2, read: function(path) {
                        if (!sk.builtinFiles || !own(sk.builtinFiles.files,path)) throw new Error('File not found')
                        return sk.builtinFiles.files[path]
                    } })
                    // Fixed bootstrap initialises Sk class globals. It never contains student code.
                    sk.importMainWithBody('<renderer>', false, 'pass', false)
                    ready = sk.misceval.asyncToPromise(function() { return sk.importModule('turtle', false, true) })
                    ready = then(ready, function(imported) { module = sk.TurtleGraphics.module
                        measureContext=root.document.createElement('canvas').getContext('2d')
                        var proto = sk.TurtleGraphics.raw.Turtle.prototype
                        var addUpdate = proto.addUpdate
                        proto.addUpdate = function() {
                            if (!disposed && ++queuedFrames > 4096) error('绘图缓存超过4096帧，请使用update()分批绘制')
                            var value = addUpdate.apply(this,arguments)
                            if (value instanceof NativePromise) then(value,function(){queuedFrames=0})
                            return value
                        }
                        return module })
                }
                return ready
            }
            function reference(value) {
                var kind = value.instance instanceof sk.TurtleGraphics.raw.Turtle ? 'Turtle' : 'Screen'
                var id = ids.get(value)
                if (!id) {
                    if (objects.size >= 128) error('最多同时创建128只海龟或画布对象')
                    id = ++nextId; ids.set(value,id); objects.set(id,{kind:kind,value:value})
                }
                return {kind:'ref',objectId:id,scope:kind}
            }
            function encode(value, depth) {
                if (depth > 8) error('绘图返回值嵌套过深')
                if (value === undefined || value === null || value === sk.builtin.none.none$) return {kind:'none'}
                if (value && value.instance) return reference(value)
                if (value instanceof sk.builtin.bool) return {kind:'bool',value:!!value.v}
                if (value instanceof sk.builtin.str) return {kind:'str',value:value.v}
                if (value instanceof sk.builtin.int_) return {kind:'int',value:sk.builtin.asnum$(value)}
                if (value instanceof sk.builtin.float_) return {kind:'float',value:value.v}
                if (value instanceof sk.builtin.tuple || value instanceof sk.builtin.list) return {kind:value instanceof sk.builtin.tuple?'tuple':'list',items:value.v.map(function(item){return encode(item,depth+1)})}
                error('不支持的绘图返回值')
            }
            function decode(value, depth, count) {
                if (!value || typeof value !== 'object' || depth > 8 || ++count.nodes > 256) error('绘图参数无效')
                var kind = value.kind
                if (kind === 'none') return sk.builtin.none.none$
                if (kind === 'bool' && typeof value.value === 'boolean') return value.value?sk.builtin.bool.true$:sk.builtin.bool.false$
                if ((kind === 'float' || kind === 'int') && typeof value.value === 'number' && Number.isFinite(value.value) && Math.abs(value.value) <= 1000000 && (kind !== 'int' || Number.isSafeInteger(value.value))) return kind === 'int' ? new sk.builtin.int_(value.value):new sk.builtin.float_(value.value)
                if (kind === 'str' && typeof value.value === 'string' && value.value.length <= 2048) return new sk.builtin.str(value.value)
                if ((kind === 'tuple'||kind === 'list') && Array.isArray(value.items) && value.items.length <= 32) {
                    var values = value.items.map(function(item){return decode(item,depth+1,count)})
                    return kind === 'tuple' ? new sk.builtin.tuple(values):new sk.builtin.list(values)
                }
                if (kind === 'ref' && Number.isSafeInteger(value.objectId)) {
                    var object = objects.get(value.objectId)
                    if (object && object.kind === value.scope) return object.value
                }
                if (kind === 'callback' && Number.isSafeInteger(value.callbackId) && value.callbackId>0 && value.callbackId<=1024) {
                    if (!callbacks.has(value.callbackId)) callbacks.set(value.callbackId,new sk.builtin.func(function() {
                        if (disposed) return sk.builtin.none.none$
                        emit({type:'turtle-event',callbackId:value.callbackId,args:Array.prototype.map.call(arguments,function(arg){return encode(arg,0)})})
                        return sk.builtin.none.none$
                    }))
                    return callbacks.get(value.callbackId)
                }
                error('绘图参数类型或大小超出限制')
            }
            function limits(packet, args) {
                var values = args.map(function(arg){
                    if (arg === sk.builtin.none.none$) return null
                    if (arg && arg.instance) return arg.instance
                    if (arg instanceof sk.builtin.func || arg instanceof sk.builtin.method) return null
                    return sk.ffi.remapToJs(arg)
                })
                var method = packet.method
                var numeric = {
                    degrees:[0],fd:[0],forward:[0],bk:[0],back:[0],backward:[0],setx:[0],sety:[0],
                    rt:[0],right:[0],lt:[0],left:[0],seth:[0],setheading:[0],circle:[0,1,2],speed:[0],
                    width:[0],pensize:[0],setundobuffer:[0],colormode:[0],tracer:[0,1],delay:[0],
                    setworldcoordinates:[0,1,2,3],ontimer:[1]
                }
                if (method==='speed' && typeof values[0]==='string' && ['fastest','fast','normal','slow','slowest'].indexOf(values[0])<0) error('speed字符串须为fastest、fast、normal、slow或slowest')
                if (own(numeric,method)) numeric[method].forEach(function(i){
                    if(method==='speed' && i===0 && typeof values[0]==='string')return
                    if (values[i]!==undefined && values[i]!==null && typeof values[i]!=='number') error('绘图数值参数须为有限数字')
                })
                if (method==='setundobuffer' && values[0]!==null && (values[0]<0||values[0]>100||values[0]%1)) error('撤销缓存须为0到100的整数')
                if (['width','pensize','dot'].indexOf(method)>=0 && values[0]!==null && values[0]!==undefined && (typeof values[0]!=='number'||values[0]<0||values[0]>256)) error('笔宽和圆点大小须在0到256之间')
                if(method==='write' && values[3]!==null && values[3]!==undefined) {
                    var font=values[3],fontSize=Array.isArray(font)?font[1]:undefined
                    if(typeof font==='string') {
                        var match=/(?:^|\s)(\d+(?:\.\d+)?)(pt|px|em|rem|%)(?:\s|$)/i.exec(font)
                        if(!match||Number(match[1])<=0||Number(match[1])>128)error('文字字号须在0到128之间')
                    }
                    if(Array.isArray(font) && fontSize!==undefined) {
                        var numericSize=typeof fontSize==='number'?fontSize:typeof fontSize==='string'&&/^\d+(?:\.\d+)?(?:pt|px|em|%)?$/.test(fontSize)?parseFloat(fontSize):NaN
                        if(!Number.isFinite(numericSize)||numericSize<=0||numericSize>128)error('文字字号须在0到128之间')
                    }
                }
                if (method==='degrees' && values[0]!==null && values[0]!==undefined && values[0]<0.001) error('角度单位须至少为0.001')
                if (method==='setup') values.forEach(function(v,i){if(i<2 && v!==null && v!==undefined && (typeof v!=='number'||v<0||v>2000))error('画布尺寸须在0到2000之间')})
                if (method==='setworldcoordinates' && (values.length<4 || Math.abs(values[2]-values[0])<1 || Math.abs(values[3]-values[1])<1 || Math.abs(values[2]-values[0])>10000 || Math.abs(values[3]-values[1])>10000)) error('世界坐标宽高须在1到10000之间')
                if (method==='circle' && ((values[2]!==null && values[2]!==undefined && (values[2]<1||values[2]>720||values[2]%1)) || Math.abs(values[1]||0)>3600 || Math.abs(values[0])>10000)) error('圆弧半径最多10000，步数须为1到720的整数，角度最多3600')
                if (method==='tracer' && values[0]!==null && values[0]!==undefined && (values[0]<0||values[0]>1000)) error('tracer帧数须在0到1000之间')
                var move=['fd','forward','bk','back','backward','setx','sety','goto_$rw$','setpos','setposition','home','circle','write']
                var turn=['rt','right','lt','left','seth','setheading']
                if (move.indexOf(method)>=0 || turn.indexOf(method)>=0) {
                    var object = packet.scope==='module'?{value:sk.misceval.callsimArray(module.getturtle)}:objects.get(packet.objectId)
                    var raw = object && object.value.instance
                    if (!raw || !(raw instanceof sk.TurtleGraphics.raw.Turtle)) error('移动接口须使用海龟对象')
                    var dx=0,dy=0,angle=0
                    if(method==='circle') {
                        var extent=values[1]===null||values[1]===undefined?raw._fullCircle:values[1]
                        var derived=values[2]
                        if(derived===null||derived===undefined) derived=1+Math.trunc(Math.min(11+Math.abs(values[0]/raw._screen.lineScale)/6,59)*Math.abs(extent)/raw._fullCircle)
                        // Guard before the old synchronous loop constructs its Promise chain, including speed(0).
                        if(!Number.isFinite(derived)||derived<1||derived>720)error('圆弧派生步数超过720，请减小角度或显式指定steps')
                    }
                    if (['goto_$rw$','setpos','setposition'].indexOf(method)>=0) {
                        var x=values[0],y=values[1]
                        if(y===null||y===undefined){y=x&&(x.y||x._y||x[1])||0;x=x&&(x.x||x._x||x[0])||0}
                        if(typeof x!=='number'||typeof y!=='number'||!Number.isFinite(x)||!Number.isFinite(y))error('坐标须为有限数字或二元坐标')
                        dx=x-raw._x;dy=y-raw._y
                    } else if(method==='write') {
                        var align=values[2]||'left'
                        if(values[1] && (align==='left'||align==='center')) {
                            var font=values[3]
                            if(Array.isArray(font)) {
                                var family=typeof font[0]==='string'?font[0]:'Arial'
                                var size=String(font[1]||'12pt')
                                if(/^\d+$/.test(size))size+='pt'
                                var style=typeof font[2]==='string'?font[2]:'normal'
                                font=[style,size,family].join(' ')
                            }
                            if(font)measureContext.font=font
                            dx=measureContext.measureText(String(values[0])).width/(align==='center'?2:1)
                        }
                    } else if(method==='setx') dx=values[0]-raw._x
                    else if(method==='sety') dy=values[0]-raw._y
                    else if(method==='home'){dx=-raw._x;dy=-raw._y;angle=360}
                    else if(method==='circle'){dx=dy=Math.abs(values[0])*2*Math.PI;angle=Math.abs(values[1]===null||values[1]===undefined?raw._fullCircle:values[1])}
                    else if(turn.indexOf(method)>=0)angle=Math.abs(values[0])*360/raw._fullCircle
                    else {dx=Math.cos(raw._radians)*values[0];dy=Math.sin(raw._radians)*values[0]}
                    var screen=raw._screen,speed=raw._computed_speed
                    var steps=speed?Math.max(1,Math.sqrt(dx*dx*Math.abs(screen.xScale)+dy*dy*Math.abs(screen.yScale))/speed)+Math.abs(angle)/speed:1
                    if (!Number.isFinite(steps)||steps>2048)error('单次绘图动画超过2048步，请提高speed或拆分绘图')
                }
                if ((method==='register_shape'||method==='addshape'||method==='bgpic') && values[0]!==null && typeof values[0]==='string' && /^(?:https?:|data:|blob:|\/\/)/i.test(values[0])) error('此运行画布仅支持已配置的图片资源')
            }
            function handle(packet) {
                if (disposed || !packet || packet.type !== 'turtle-request' || !Number.isSafeInteger(packet.requestId) || packet.requestId <= 0) return
                if (++total>10000 || pending>=32) { emit({type:'turtle-result',requestId:packet.requestId,error:{name:'ValueError',message:'绘图请求超过本次运行限制'}}); return }
                pending++
                var result = then(initialise(),function() {
                    if (disposed) return
                    if (packet.op === 'init') return {schema:SCHEMA}
                    if (packet.op !== 'call' && packet.op !== 'create') error('未知绘图操作')
                    if (!own(SCHEMA,packet.scope) || !Array.isArray(packet.args)||packet.args.length>8) error('绘图接口无效')
                    var count={nodes:0}
                    var args = packet.args.map(function(value){return decode(value,0,count)})
                    var fn
                    if (packet.op === 'create') {
                        if (packet.scope!=='Turtle' && packet.scope!=='Screen') error('未知绘图对象')
                        if (args.length > (packet.scope==='Turtle'?1:0)) error('绘图构造参数无效')
                        fn = module[packet.scope]
                    } else {
                        if (!own(SCHEMA[packet.scope],packet.method)) error('绘图方法不在白名单中')
                        if (args.length>SCHEMA[packet.scope][packet.method].max) error('绘图参数过多')
                        limits(packet,args)
                        if (packet.scope==='module') fn = module[packet.method]
                        else {
                            var object=objects.get(packet.objectId)
                            if (!object||object.kind!==packet.scope) error('绘图对象已失效')
                            fn=sk.abstr.gattr(object.value,new sk.builtin.str(packet.method),false)
                        }
                    }
                    return then(sk.misceval.asyncToPromise(function(){return sk.misceval.callsimOrSuspendArray(fn,args)}),function(value){
                        if (!graphicsSent && target.querySelector('canvas')) { graphicsSent=true; emit({type:'graphics'}) }
                        return {value:encode(value,0)}
                    })
                })
                then(result,function(reply){pending--; if(!disposed && reply) emit(Object.assign({type:'turtle-result',requestId:packet.requestId},reply))},function(err){pending--; if(!disposed) emit({type:'turtle-result',requestId:packet.requestId,error:{name:err && err.tp$name || 'RuntimeError',message:String(err && err.args && err.args.v && err.args.v[0] ? sk.ffi.remapToJs(err.args.v[0]) : err).slice(0,2048)}})})
            }
            function dispose() {
                if(disposed)return
                disposed=true
                if (sk.TurtleGraphics && sk.TurtleGraphics.reset) sk.TurtleGraphics.reset()
                objects.clear();callbacks.clear()
            }
            return {handle:handle,dispose:dispose}
        }
    }
}(window))
