package org.jeecg.common.util;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.io.OutputStream;
import java.net.URLEncoder;
import java.math.BigInteger;
import java.nio.ByteBuffer;
import java.nio.channels.SeekableByteChannel;
import java.nio.file.*;
import java.util.Locale;

/** Confined local storage and bounded single-range streaming. Call only after authorization. */
public final class LocalFileDownload {
    private LocalFileDownload() { }

    public static boolean validKey(String key) {
        if (key == null || key.isEmpty() || key.length() > 1024 || key.startsWith("/")
                || key.contains("\\") || key.contains(":") || key.chars().anyMatch(c -> c < 32 || c == 127)) return false;
        for (String part : key.split("/", -1)) if (part.isEmpty() || part.equals(".") || part.equals("..")) return false;
        return true;
    }

    public static void serve(String root, String key, HttpServletRequest request, HttpServletResponse response) throws IOException {
        if (!validKey(key)) { response.setStatus(404); return; }
        Path base = Paths.get(root).toRealPath();
        Path file = base;
        for (String part : key.split("/")) {
            file = file.resolve(part);
            if (Files.isSymbolicLink(file)) { response.setStatus(404); return; }
        }
        if (!Files.isRegularFile(file, LinkOption.NOFOLLOW_LINKS) || !file.toRealPath().startsWith(base)) {
            response.setStatus(404); return;
        }
        // NOFOLLOW_LINKS also rejects a final-component swap before opening.
        // Upload storage directories must remain writable only by this service.
        try (SeekableByteChannel channel = Files.newByteChannel(file, StandardOpenOption.READ, LinkOption.NOFOLLOW_LINKS)) {
            long length = channel.size(), start = 0, end = length - 1;
            String range = request.getHeader("Range");
            boolean partial = false;
            // No validators are emitted: If-Range cannot match. Multiple ranges use full 200.
            if ("GET".equals(request.getMethod()) && range != null && range.startsWith("bytes=")
                    && !range.contains(",") && request.getHeader("If-Range") == null) {
                try {
                    String value = range.substring(6);
                    if (!value.matches("[0-9]*-[0-9]*")) throw new IllegalArgumentException();
                    String[] parts = value.split("-", -1);
                    if (parts[0].isEmpty()) {
                        long suffix = new BigInteger(parts[1]).min(BigInteger.valueOf(length)).longValue();
                        if (suffix <= 0) throw new IllegalArgumentException();
                        start = Math.max(0, length - suffix);
                    } else {
                        start = Long.parseLong(parts[0]);
                        if (!parts[1].isEmpty()) end = new BigInteger(parts[1]).min(BigInteger.valueOf(end)).longValue();
                    }
                    if (length == 0 || start >= length || end < start) throw new IllegalArgumentException();
                    partial = true;
                } catch (IllegalArgumentException invalid) {
                    response.setStatus(416);
                    response.setHeader("Content-Range", "bytes */" + length);
                    response.setContentLengthLong(0);
                    return;
                }
            }
            String mime = mime(file.getFileName().toString());
            response.setContentType(mime);
            response.setHeader("X-Content-Type-Options", "nosniff");
            response.setHeader("Content-Security-Policy", "sandbox; default-src 'none'");
            response.setHeader("Content-Disposition", ("application/octet-stream".equals(mime) ? "attachment" : "inline")
                    + "; filename*=UTF-8''" + URLEncoder.encode(file.getFileName().toString(), "UTF-8").replace("+", "%20"));
            response.setHeader("Accept-Ranges", "bytes");
            response.setStatus(partial ? 206 : 200);
            if (partial) response.setHeader("Content-Range", "bytes " + start + "-" + end + "/" + length);
            long remaining = length == 0 ? 0 : end - start + 1;
            response.setContentLengthLong(remaining);
            if ("HEAD".equals(request.getMethod())) return;
            channel.position(start);
            ByteBuffer buffer = ByteBuffer.allocate(16384);
            OutputStream output = response.getOutputStream();
            while (remaining > 0) {
                buffer.clear();
                buffer.limit((int) Math.min(buffer.capacity(), remaining));
                int count = channel.read(buffer);
                if (count < 0) throw new IOException("File changed during download");
                output.write(buffer.array(), 0, count);
                remaining -= count;
            }
        }
    }

    private static String mime(String name) {
        String suffix = name.substring(name.lastIndexOf('.') + 1).toLowerCase(Locale.ROOT);
        switch (suffix) {
            case "png": return "image/png";
            case "jpg": case "jpeg": return "image/jpeg";
            case "gif": return "image/gif";
            case "webp": return "image/webp";
            case "mp4": return "video/mp4";
            case "webm": return "video/webm";
            case "mp3": return "audio/mpeg";
            case "wav": return "audio/wav";
            case "ogg": return "audio/ogg";
            case "pdf": return "application/pdf";
            default: return "application/octet-stream";
        }
    }
}
