package org.jeecg.common.util;

import org.springframework.web.multipart.MultipartFile;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardOpenOption;

/** Store a new local upload under the configured root, without following child links. */
public final class LocalFileUpload {
    private LocalFileUpload() { }

    public static String save(String uploadRoot, String directory, MultipartFile file) throws IOException {
        String relative = directory == null ? "" : directory.trim();
        if (relative.startsWith("/") || relative.contains("\\") || relative.contains(":")
                || hasControlCharacter(relative)) {
            throw new IllegalArgumentException("上传目录不合法");
        }
        String[] segments = relative.split("/");
        for (String segment : segments) {
            if (".".equals(segment) || "..".equals(segment)) {
                throw new IllegalArgumentException("上传目录不合法");
            }
        }
        if (file == null || file.getOriginalFilename() == null) {
            throw new IllegalArgumentException("请选择上传文件");
        }
        String originalName = CommonUtils.getFileName(file.getOriginalFilename());
        if (originalName.isEmpty() || hasControlCharacter(originalName)) {
            throw new IllegalArgumentException("上传文件名不合法");
        }
        String extension = originalName.contains(".") ? originalName.substring(originalName.indexOf('.')) : "";
        // A client filename is never the storage name; CREATE_NEW also prevents overwrites.
        String storedName = java.util.UUID.randomUUID().toString().replace("-", "") + extension;
        Files.createDirectories(Paths.get(uploadRoot));
        Path root = Paths.get(uploadRoot).toRealPath();
        Path parent = root;
        for (String segment : segments) {
            if (segment.isEmpty()) continue;
            parent = parent.resolve(segment);
            if (Files.isSymbolicLink(parent)) {
                throw new IllegalArgumentException("上传目录不能包含符号链接");
            }
            if (!Files.exists(parent, LinkOption.NOFOLLOW_LINKS)) {
                try {
                    Files.createDirectory(parent);
                } catch (java.nio.file.FileAlreadyExistsException concurrentCreation) {
                    // Another upload can create the same directory; validate it below.
                }
            }
            if (!Files.isDirectory(parent, LinkOption.NOFOLLOW_LINKS) || !parent.toRealPath().startsWith(root)) {
                throw new IllegalArgumentException("上传目录不可用");
            }
        }
        Path destination = parent.resolve(storedName);
        boolean created = false;
        try (InputStream input = file.getInputStream();
             OutputStream output = Files.newOutputStream(destination, StandardOpenOption.CREATE_NEW, StandardOpenOption.WRITE)) {
            created = true;
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) {
                output.write(buffer, 0, count);
            }
        } catch (IOException | RuntimeException error) {
            if (created) {
                try {
                    Files.deleteIfExists(destination);
                } catch (IOException cleanupError) {
                    error.addSuppressed(cleanupError);
                }
            }
            throw error;
        }
        return root.relativize(destination).toString().replace(File.separatorChar, '/');
    }

    private static boolean hasControlCharacter(String value) {
        return value.chars().anyMatch(c -> c < 32 || c == 127);
    }
}
