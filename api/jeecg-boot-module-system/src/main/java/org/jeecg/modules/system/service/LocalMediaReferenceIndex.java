package org.jeecg.modules.system.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.jeecg.common.util.LocalFileDownload;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.transaction.support.TransactionTemplate;

import javax.annotation.PostConstruct;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import java.util.function.Supplier;

/** Indexed candidates only. The downloader still validates live content and object access. */
@Service
public class LocalMediaReferenceIndex {
    private static final int VERSION = 1;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private ObjectMapper json;
    @Autowired private LocalFileReferenceResolver resolver;
    @Autowired private PlatformTransactionManager transactionManager;
    @Value("${jeecg.path.staticDomain}") private String staticDomain;
    @Value("${jeecg.media.rebuild-index:false}") private boolean rebuildAtStartup;

    @PostConstruct
    public void initialize() { rebuild(rebuildAtStartup); }

    /** One initialization after migration; later boots only inspect the state row. */
    public int rebuild(boolean force) {
        return new TransactionTemplate(transactionManager).execute(status -> {
            Map<String, Object> state = jdbc.queryForMap("SELECT version,static_domain FROM sys_local_file_reference_state WHERE id=1 FOR UPDATE");
            if (!Integer.valueOf(0).equals(state.get("version")) && !Integer.valueOf(VERSION).equals(state.get("version")))
                throw new IllegalStateException("Unsupported local media index version; refusing to rewrite it");
            if (!force && Integer.valueOf(VERSION).equals(state.get("version"))) {
                requireDomain(state);
                return 0;
            }
            jdbc.update("DELETE FROM sys_local_file_reference");
            int count = 0;
            for (LocalMediaSource source : LocalMediaSource.values()) {
                String previous = null;
                while (true) {
                    List<Map<String, Object>> rows = previous == null
                            ? jdbc.queryForList("SELECT * FROM " + source.table + " ORDER BY id LIMIT 200")
                            : jdbc.queryForList("SELECT * FROM " + source.table + " WHERE id>? ORDER BY id LIMIT 200", previous);
                    if (rows.isEmpty()) break;
                    for (Map<String, Object> row : rows) count += insert(source, row);
                    previous = text(rows.get(rows.size() - 1), "id");
                }
            }
            jdbc.update("UPDATE sys_local_file_reference_state SET version=?,static_domain=? WHERE id=1", VERSION, staticDomain);
            return count;
        });
    }

    private void requireDomain(Map<String, Object> state) {
        if (!Objects.equals(staticDomain, state.get("static_domain")))
            throw new IllegalStateException("Local media domain changed; rebuild the local media reference index before starting this candidate");
    }

    /** Always acquire the gate before any source write, including custom service commands. */
    public void lockWrites() {
        if (!TransactionSynchronizationManager.isActualTransactionActive())
            throw new IllegalStateException("Media references must be written in the business transaction");
        Map<String, Object> state = jdbc.queryForMap("SELECT version,static_domain FROM sys_local_file_reference_state WHERE id=1 LOCK IN SHARE MODE");
        if (!Integer.valueOf(VERSION).equals(state.get("version"))) throw new IllegalStateException("Local media index is not ready");
        requireDomain(state);
    }

    public <T> T write(Supplier<T> command) {
        return new TransactionTemplate(transactionManager).execute(status -> {
            lockWrites();
            return command.get();
        });
    }

    public void replace(LocalMediaSource source, String id) {
        if (!TransactionSynchronizationManager.isActualTransactionActive())
            throw new IllegalStateException("Media references must be written in the business transaction");
        List<Map<String, Object>> rows = jdbc.queryForList("SELECT * FROM " + source.table + " WHERE id=? FOR UPDATE", id);
        jdbc.update("DELETE FROM sys_local_file_reference WHERE source_type=? AND source_id=?", source.table, id);
        if (!rows.isEmpty()) insert(source, rows.get(0));
    }

    private int insert(LocalMediaSource source, Map<String, Object> row) {
        int count = 0;
        for (Map.Entry<String, Set<String>> field : references(source, row).entrySet()) {
            for (String value : field.getValue()) {
                jdbc.update("INSERT INTO sys_local_file_reference (source_type,source_id,field_name,reference_kind,reference_hash,reference_value) VALUES (?,?,?,?,?,?)",
                        source.table, text(row, "id"), field.getKey(), source == LocalMediaSource.HISTORY ? "file" : "key", hash(value), value);
                count++;
            }
        }
        return count;
    }

    Map<String, Set<String>> references(LocalMediaSource source, Map<String, Object> row) {
        Map<String, Set<String>> found = new LinkedHashMap<>();
        if (source == LocalMediaSource.HISTORY) {
            if (!"teaching_work".equals(text(row, "data_table"))) return found;
            try {
                JsonNode previous = json.readTree(text(row, "data_content"));
                if (previous != null) for (String field : Arrays.asList("workFile", "workCover")) {
                    String value = previous.path(field).asText("");
                    if (!value.isEmpty()) found.put(field, Collections.singleton(value));
                }
            } catch (java.io.IOException ignored) { /* Invalid old JSON never granted file access. */ }
        } else {
            for (String field : source.fields) {
                Set<String> keys = new LinkedHashSet<>();
                for (String key : resolver.resolve(text(row, field)).keys()) if (LocalFileDownload.validKey(key)) keys.add(key);
                found.put(field, keys);
            }
        }
        return found;
    }

    /** A fixed number of indexed selects, independent of unrelated source rows. */
    public Map<LocalMediaSource, List<Map<String, Object>>> candidates(String kind, Collection<String> values) {
        Map<LocalMediaSource, Set<String>> ids = new EnumMap<>(LocalMediaSource.class);
        for (String value : new LinkedHashSet<>(values)) {
            for (Map<String, Object> reference : jdbc.queryForList(
                    "SELECT source_type,source_id,reference_value FROM sys_local_file_reference WHERE reference_kind=? AND reference_hash=?", kind, hash(value))) {
                // Hashes and database collations select candidates, never establish equality.
                if (!value.equals(text(reference, "reference_value"))) continue;
                LocalMediaSource source = LocalMediaSource.forTable(text(reference, "source_type"));
                ids.computeIfAbsent(source, unused -> new LinkedHashSet<>()).add(text(reference, "source_id"));
            }
        }
        Map<LocalMediaSource, List<Map<String, Object>>> result = new EnumMap<>(LocalMediaSource.class);
        for (Map.Entry<LocalMediaSource, Set<String>> entry : ids.entrySet()) {
            List<String> sourceIds = new ArrayList<>(entry.getValue());
            List<Map<String, Object>> rows = new ArrayList<>();
            for (int start = 0; start < sourceIds.size(); start += 200) {
                List<String> batch = sourceIds.subList(start, Math.min(start + 200, sourceIds.size()));
                rows.addAll(jdbc.queryForList("SELECT * FROM " + entry.getKey().table + " WHERE id IN ("
                        + String.join(",", Collections.nCopies(batch.size(), "?")) + ")", batch.toArray()));
            }
            result.put(entry.getKey(), rows);
        }
        return result;
    }

    public static String hash(String value) {
        try {
            byte[] bytes = MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex = new StringBuilder(64);
            for (byte b : bytes) hex.append(String.format("%02x", b & 255));
            return hex.toString();
        } catch (java.security.NoSuchAlgorithmException impossible) { throw new IllegalStateException(impossible); }
    }

    private static String text(Map<String, Object> row, String field) {
        Object value = row.get(field);
        return value == null ? "" : value.toString();
    }
}
