import org.jeecg.common.util.LocalFileUpload;
import org.springframework.web.multipart.MultipartFile;
import java.io.*;
import java.nio.file.*;
import java.util.stream.Stream;

/** Fault injection against the exact utility packaged in the candidate JAR. */
public class VerifyLocalUploadFailure {
    public static void main(String[] args) throws Exception {
        Path root = Paths.get(args[0]);
        Files.createDirectory(root);
        Path sentinel = root.resolve("sentinel.txt");
        Files.write(sentinel, new byte[]{7, 8, 9});
        try {
            for (final int fault : new int[]{0, 1, 2}) {
                MultipartFile upload = new MultipartFile() {
                    public String getName() { return "file"; }
                    public String getOriginalFilename() { return "fault.sb3"; }
                    public String getContentType() { return "application/octet-stream"; }
                    public boolean isEmpty() { return false; }
                    public long getSize() { return 32; }
                    public byte[] getBytes() { throw new AssertionError("Upload must stream instead of materializing all bytes"); }
                    public void transferTo(File dest) { throw new AssertionError("Unexpected transferTo"); }
                    public InputStream getInputStream() throws IOException {
                        if (fault == 0) throw new IOException("synthetic open failure");
                        return new InputStream() {
                            private boolean emitted;
                            public int read() { throw new AssertionError("Expected buffered streaming"); }
                            public int read(byte[] buffer) throws IOException {
                                if (!emitted) {
                                    emitted = true;
                                    for (int i = 0; i < 32; i++) buffer[i] = 42;
                                    return 32;
                                }
                                if (fault == 1) throw new IOException("synthetic failure after partial write");
                                return -1;
                            }
                            public void close() throws IOException {
                                if (fault == 2) throw new IOException("synthetic close failure");
                            }
                        };
                    }
                };
                boolean failed = false;
                try { LocalFileUpload.save(root.toString(), "", upload); }
                catch (IOException expected) { failed = true; }
                long fileCount;
                try (Stream<Path> entries = Files.list(root)) { fileCount = entries.count(); }
                if (!failed || fileCount != 1 || !java.util.Arrays.equals(Files.readAllBytes(sentinel), new byte[]{7, 8, 9})) {
                    throw new AssertionError("Fault " + fault + " left a partial upload or changed original bytes");
                }
                System.out.println("PASS streaming fault " + fault + ": original bytes intact, no partial upload");
            }
        } finally {
            Files.deleteIfExists(sentinel);
            Files.delete(root);
        }
    }
}
