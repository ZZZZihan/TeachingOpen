/* Register the existing webpack modules without running either Vue entry. */
(function (root) {
    'use strict'
    var modules = Object.create(null)
    var cache = Object.create(null)
    root.webpackJsonp = function (chunks, additions) {
        Object.keys(additions).forEach(function (id) { modules[id] = additions[id] })
    }
    function requireModule (id) {
        if (cache[id]) return cache[id].exports
        if (!modules[id]) throw new Error('Python 运行环境缺少模块')
        var module = cache[id] = { exports: {}, i: id, l: false }
        modules[id].call(module.exports, module, module.exports, requireModule)
        module.l = true
        return module.exports
    }
    requireModule.m = modules
    requireModule.c = cache
    requireModule.o = function (object, key) { return Object.prototype.hasOwnProperty.call(object, key) }
    requireModule.d = function (object, key, getter) {
        if (!requireModule.o(object, key)) Object.defineProperty(object, key, { enumerable: true, get: getter })
    }
    requireModule.n = function (module) {
        var getter = module && module.__esModule ? function () { return module.default } : function () { return module }
        requireModule.d(getter, 'a', getter)
        return getter
    }
    requireModule.p = './'
    root.TeachingPythonRuntime = function () {
        requireModule('rONZ')
        requireModule('21Q0')
        delete root.TeachingPythonRuntime
        delete root.webpackJsonp
        return root.Sk
    }
}(window))
