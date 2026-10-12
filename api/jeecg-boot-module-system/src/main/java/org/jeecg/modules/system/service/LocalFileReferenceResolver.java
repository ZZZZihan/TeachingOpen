package org.jeecg.modules.system.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.util.HtmlUtils;

import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** One exact URL/HTML/JSON interpretation for read authorization and new references. */
@Component
public class LocalFileReferenceResolver {
    @Autowired private ObjectMapper json;
    @Value("${jeecg.path.staticDomain}") private String staticDomain;
    private static final Pattern HTML_LINK = Pattern.compile("(?i)\\b(?:src|href|poster)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))");

    public References resolve(String value) {
        References result = new References();
        if (value == null || value.isEmpty()) return result;
        for (String part : value.split(",")) add(part.trim(), result);
        Matcher links = HTML_LINK.matcher(value);
        while (links.find()) {
            String link = links.group(1) != null ? links.group(1) : links.group(2) != null ? links.group(2) : links.group(3);
            add(HtmlUtils.htmlUnescape(link), result);
        }
        if (value.trim().startsWith("{") || value.trim().startsWith("[")) {
            try { addJson(json.readTree(value), result, 0); } catch (java.io.IOException invalid) { /* No JSON references. */ }
        }
        return result;
    }

    private void addJson(JsonNode node, References result, int depth) {
        if (node == null || depth > 20) return;
        if (node.isTextual()) add(node.asText(), result);
        if (node.isContainerNode()) for (JsonNode child : node) addJson(child, result, depth + 1);
    }

    private void add(String value, References result) {
        if (value.isEmpty()) return;
        // Legacy values can be a storage key rather than a URL.
        result.keys.add(value);
        try {
            URI reference = new URI(value);
            URI configured = new URI(staticDomain.replaceAll("/+$", ""));
            if (!Objects.equals(reference.getScheme(), configured.getScheme())
                    || !Objects.equals(reference.getRawAuthority(), configured.getRawAuthority())
                    || !validUtf8Escapes(reference.getRawPath())) return;
            String prefix = configured.getPath() + "/";
            String path = reference.getPath();
            if (path != null && path.startsWith(prefix) && path.length() > prefix.length()) {
                String key = path.substring(prefix.length());
                result.keys.add(key);
                result.localUrls.add(key);
            }
        } catch (java.net.URISyntaxException invalid) { /* Cannot identify a local URL. */ }
    }

    private boolean validUtf8Escapes(String rawPath) {
        if (rawPath == null) return false;
        int index = rawPath.indexOf('%');
        if (index < 0) return true;
        byte[] octets = new byte[(rawPath.length() - index) / 3];
        while (index >= 0) {
            int count = 0;
            do {
                octets[count++] = (byte) ((Character.digit(rawPath.charAt(index + 1), 16) << 4)
                        | Character.digit(rawPath.charAt(index + 2), 16));
                index += 3;
            } while (index < rawPath.length() && rawPath.charAt(index) == '%');
            try {
                StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(octets, 0, count));
            } catch (CharacterCodingException invalid) { return false; }
            index = rawPath.indexOf('%', index);
        }
        return true;
    }

    public static class References {
        private final Set<String> keys = new TreeSet<>();
        private final Set<String> localUrls = new TreeSet<>();
        public Set<String> keys() { return Collections.unmodifiableSet(keys); }
        public Set<String> localUrls() { return Collections.unmodifiableSet(localUrls); }
    }
}
