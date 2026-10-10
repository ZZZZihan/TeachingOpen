/* Shared by the prebuilt editor and player. This bounds display output, not Python execution. */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory()
    else root.TeachingPythonOutput = factory()
}(typeof window !== 'undefined' ? window : this, function () {
    'use strict'
    // UTF-16 units, excluding the fixed notice. Never cut a valid surrogate pair.
    var MAX_UNITS = 20000
    var NOTICE = '输出较长，已停止显示后续内容（显示上限约 2 万字符）。程序仍可继续运行；清空或重新运行可重置输出区。\n\n'
    var buffers = new WeakMap()

    function clear (node) {
        if (!node) return
        node.textContent = ''
        buffers.delete(node)
    }

    function append (node, value) {
        if (!node) return
        var buffer = buffers.get(node)
        if (!buffer || buffer.text.parentNode !== node) {
            clear(node)
            buffer = { text: node.ownerDocument.createTextNode(''), truncated: false }
            node.appendChild(buffer.text)
            buffers.set(node, buffer)
        }
        if (buffer.truncated) return
        var text = String(value)
        var remaining = MAX_UNITS - buffer.text.length
        var length = Math.min(remaining, text.length)
        if (length < text.length && length > 0) {
            var last = text.charCodeAt(length - 1)
            var next = text.charCodeAt(length)
            if (last >= 0xD800 && last <= 0xDBFF && next >= 0xDC00 && next <= 0xDFFF) length--
        }
        if (length) buffer.text.appendData(text.slice(0, length))
        if (length < text.length) {
            // A pair can also straddle two output calls at the display boundary.
            var tail = buffer.text.data.charCodeAt(buffer.text.length - 1)
            var first = text.charCodeAt(length)
            if (tail >= 0xD800 && tail <= 0xDBFF && first >= 0xDC00 && first <= 0xDFFF) {
                buffer.text.deleteData(buffer.text.length - 1, 1)
            }
            var notice = node.ownerDocument.createElement('span')
            notice.className = 'python-output-notice'
            notice.textContent = NOTICE
            node.insertBefore(notice, buffer.text)
            buffer.truncated = true
        }
    }

    return { append: append, clear: clear, maxUnits: MAX_UNITS, notice: NOTICE }
}))
