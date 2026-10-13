package org.jeecg.modules.teaching.util;

import java.net.URI;
import java.net.URISyntaxException;
import java.util.regex.Pattern;

/** Navigation destinations, independent of caller-controlled routing/window flags. */
public final class TeachingMenuUrlPolicy {
    private static final Pattern ENCODED_CONTROL = Pattern.compile("%(?:0[0-9a-f]|1[0-9a-f]|7f|5c)", Pattern.CASE_INSENSITIVE);
    private TeachingMenuUrlPolicy() { }
    /** Null means unsafe; empty string is a non-navigating group label. */
    public static String safeUrl(String input) {
        if (input == null) return "";
        if (input.length() > 255) return null;
        for (int i = 0; i < input.length(); i++) if (input.charAt(i) < 32 || input.charAt(i) == 127 || input.charAt(i) == '\\') return null;
        String value = input.trim();
        if (value.isEmpty()) return "";
        for (int i = 0; i < value.length(); i++) if (Character.isWhitespace(value.charAt(i)) || Character.isSpaceChar(value.charAt(i))) return null;
        if (ENCODED_CONTROL.matcher(value).find()) return null;
        try {
            URI uri = new URI(value);
            if (value.startsWith("/") && !value.startsWith("//") && uri.getScheme() == null && uri.getRawAuthority() == null) {
                String path = uri.getPath();
                return path != null && !path.startsWith("//") && path.indexOf('\\') < 0 ? value : null;
            }
            return "https".equalsIgnoreCase(uri.getScheme()) && value.regionMatches(true, 0, "https://", 0, 8)
                    && uri.getHost() != null && !uri.getHost().isEmpty() && uri.getRawUserInfo() == null && uri.getPort() <= 65535 ? value : null;
        } catch (URISyntaxException invalid) { return null; }
    }
    public static boolean local(String url) { return url != null && url.startsWith("/") && !url.startsWith("//"); }
}
