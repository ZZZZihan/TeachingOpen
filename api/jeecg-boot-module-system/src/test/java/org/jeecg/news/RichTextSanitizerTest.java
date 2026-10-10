package org.jeecg.news;

import org.jeecg.modules.teaching.util.RichTextSanitizer;
import org.jsoup.Jsoup;
import org.jsoup.nodes.Element;
import org.junit.Test;
import static org.junit.Assert.*;

public class RichTextSanitizerTest {
    @Test public void removesExecutableMarkupAndEncodedProtocols() {
        String[] attacks = {
                "<img src=x onerror=alert(1)><script>alert(2)</script>",
                "<a href='java&#x73;cript:alert(1)' onclick=alert(2)>x</a>",
                "<a href='java&#10;script:alert(1)'>x</a><iframe srcdoc='<script>alert(1)</script>'></iframe>",
                "<svg><a xlink:href='javascript:alert(1)'>x</a></svg><math><mtext><img src=x onerror=alert(2)></mtext></math>",
                "<img src='data:image/svg+xml;base64,PHN2ZyBvbmxvYWQ9YWxlcnQoMSk+' data-mce-src='javascript:alert(1)'>",
                "<p style='background-image:url(javascript:alert(1));color:expression(alert(2))'>safe</p>",
                "<video src='javascript:alert(1)' onloadeddata=alert(1)><source src='data:text/html,evil'></video>",
                "<form id=location><input name=href></form><object data='javascript:alert(1)'></object>"
        };
        for (String attack : attacks) {
            String clean = RichTextSanitizer.sanitize(attack);
            assertEquals(clean, RichTextSanitizer.sanitize(clean));
            for (Element element : Jsoup.parseBodyFragment(clean).getAllElements()) {
                assertFalse(element.normalName().matches("script|iframe|svg|math|object|form|input"));
                element.attributes().forEach(attribute -> {
                    assertFalse(attribute.getKey().startsWith("on"));
                    assertFalse(attribute.getKey().startsWith("data-"));
                    assertFalse(attribute.getValue().toLowerCase().contains("javascript:"));
                    assertFalse(attribute.getValue().toLowerCase().contains("expression("));
                });
            }
        }
    }

    @Test public void retainsNormalNewsFormattingAndUploadedMedia() {
        String html = "<h2 style='text-align:center;color:#123abc'>标题</h2><p><b>粗体</b><i>斜体</i><u>下划线</u></p>"
                + "<ul><li>列表</li></ul><table><tbody><tr><th>标题</th><td colspan='2'>内容</td></tr></tbody></table>"
                + "<img src='/api/sys/common/static/a.png' alt='图片'><img src='data:image/png;base64,AAAA'>"
                + "<video src='https://example.test/a.mp4' controls><source src='/media/a.mp4' type='video/mp4'></video>"
                + "<pre><code class='language-java'>System.out.println(&quot;hi&quot;);</code></pre>"
                + "<a href='https://example.test' target='_blank'>链接</a>";
        String clean = RichTextSanitizer.sanitize(html);
        Element body = Jsoup.parseBodyFragment(clean).body();
        assertEquals("text-align:center;color:#123abc;", body.selectFirst("h2").attr("style"));
        assertEquals("2", body.selectFirst("td").attr("colspan"));
        assertEquals("/api/sys/common/static/a.png", body.selectFirst("img").attr("src"));
        assertEquals("data:image/png;base64,AAAA", body.select("img").get(1).attr("src"));
        assertEquals("/media/a.mp4", body.selectFirst("source").attr("src"));
        assertTrue(body.selectFirst("video").hasAttr("controls"));
        assertEquals("language-java", body.selectFirst("code").className());
        assertEquals("noopener noreferrer", body.selectFirst("a").attr("rel"));
        assertEquals(clean, RichTextSanitizer.sanitize(clean));
    }

    @Test public void nullAndEmptyContentKeepTheExistingPartialUpdateContract() {
        assertNull(RichTextSanitizer.sanitize(null));
        assertEquals("", RichTextSanitizer.sanitize(""));
    }
}
