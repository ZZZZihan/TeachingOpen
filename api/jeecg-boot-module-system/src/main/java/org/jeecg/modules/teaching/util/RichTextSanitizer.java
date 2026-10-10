package org.jeecg.modules.teaching.util;

import org.jsoup.Jsoup;
import org.jsoup.nodes.Document;
import org.jsoup.nodes.Element;
import org.jsoup.safety.Cleaner;
import org.jsoup.safety.Safelist;

/** Fixed HTML policy for authored news. Parse HTML, then retain only display markup. */
public final class RichTextSanitizer {
    private static final Safelist POLICY = new Safelist()
            .addTags("p", "div", "span", "br", "strong", "b", "em", "i", "u", "s", "strike", "sub", "sup",
                    "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code", "ul", "ol", "li", "hr",
                    "a", "img", "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
                    "video", "source")
            .addAttributes(":all", "style", "title")
            .addAttributes("a", "href", "target")
            .addAttributes("img", "src", "alt", "width", "height")
            .addAttributes("video", "src", "poster", "width", "height", "controls", "preload")
            .addAttributes("source", "src", "type")
            .addAttributes("td", "colspan", "rowspan", "colwidth")
            .addAttributes("th", "colspan", "rowspan", "colwidth", "scope")
            .addAttributes("col", "span", "width")
            .addAttributes("ol", "start")
            .addAttributes("code", "class")
            .addProtocols("a", "href", "http", "https", "mailto", "#")
            .addProtocols("img", "src", "http", "https", "data")
            .addProtocols("video", "src", "http", "https")
            .addProtocols("video", "poster", "http", "https")
            .addProtocols("source", "src", "http", "https")
            .preserveRelativeLinks(true);

    private RichTextSanitizer() { }

    public static String sanitize(String html) {
        if (html == null || html.isEmpty()) return html;
        // A fixed base lets Cleaner validate ordinary relative uploaded-media URLs.
        Document clean = new Cleaner(POLICY).clean(Jsoup.parseBodyFragment(html, "https://rich-text.invalid/"));
        clean.outputSettings().prettyPrint(false);
        for (Element element : clean.body().getAllElements()) {
            if (element.hasAttr("style")) {
                String style = safeStyle(element.attr("style"));
                if (style.isEmpty()) element.removeAttr("style"); else element.attr("style", style);
            }
            if (element.hasAttr("class") && !element.attr("class").matches("language-[a-zA-Z0-9+#-]+")) element.removeAttr("class");
            if (element.normalName().equals("img") && element.attr("src").regionMatches(true, 0, "data:", 0, 5)
                    && !element.attr("src").matches("(?i)data:image/(png|jpeg|gif|webp);base64,[a-z0-9+/=\\r\\n]+")) element.removeAttr("src");
            if (element.normalName().equals("a")) {
                if ("_blank".equals(element.attr("target"))) element.attr("rel", "noopener noreferrer");
                else element.removeAttr("target");
            }
            if (element.normalName().equals("video")) {
                element.attr("controls", "");
                element.attr("preload", "metadata");
            }
        }
        return clean.body().html();
    }

    // Only simple presentation values are accepted; URLs, CSS escapes and functions other than rgb are excluded.
    private static String safeStyle(String style) {
        StringBuilder result = new StringBuilder();
        for (String declaration : style.split(";")) {
            String[] pair = declaration.split(":", 2);
            if (pair.length != 2) continue;
            String name = pair[0].trim().toLowerCase(java.util.Locale.ROOT);
            String value = pair[1].trim().toLowerCase(java.util.Locale.ROOT);
            boolean safe = false;
            if (name.equals("color") || name.equals("background-color"))
                safe = value.matches("#[0-9a-f]{3,8}|(?:black|white|red|green|blue|yellow|gray|grey|orange|purple|pink|transparent)|rgba?\\([0-9.,% ]+\\)");
            else if (name.equals("text-align")) safe = value.matches("left|center|right|justify");
            else if (name.equals("font-weight")) safe = value.matches("normal|bold|[1-9]00");
            else if (name.equals("font-style")) safe = value.matches("normal|italic");
            else if (name.equals("text-decoration")) safe = value.matches("none|underline|line-through");
            else if (name.equals("vertical-align")) safe = value.matches("top|middle|bottom|baseline|sub|super");
            else if (name.equals("list-style-type")) safe = value.matches("disc|circle|square|decimal|lower-alpha|upper-alpha|lower-roman|upper-roman");
            else if (name.equals("width") || name.equals("height") || name.equals("max-width") || name.equals("font-size") || name.equals("margin-left") || name.equals("padding-left"))
                safe = value.matches("[0-9]+(?:\\.[0-9]+)?(?:px|em|rem|%)|auto");
            if (safe) result.append(name).append(':').append(value).append(';');
        }
        return result.toString();
    }
}
