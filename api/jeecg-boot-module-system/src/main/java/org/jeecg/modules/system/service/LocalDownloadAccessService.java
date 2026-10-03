package org.jeecg.modules.system.service;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.shiro.authz.AuthorizationException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.util.HtmlUtils;
import org.springframework.web.util.UriUtils;

import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Resolve local bytes through current authoritative resource relationships on every request. */
@Service
public class LocalDownloadAccessService {
    @Autowired private ISysFileService files;
    @Autowired private TeachingWorkMapper works;
    @Autowired private TeachingAccessService access;
    @Autowired private ISysUserDepartService departments;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private ObjectMapper json;
    @Value("${jeecg.path.staticDomain}") private String staticDomain;
    private static final Pattern HTML_LINK = Pattern.compile("(?i)\\b(?:src|href|poster)\\s*=\\s*(?:\"([^\"]*)\"|'([^']*)'|([^\\s>]+))");

    public int status(String key) {
        LoginUser user = access.currentUser();
        if (user != null && access.isAdministrator()) return 200;
        List<SysFile> records = files.list(new QueryWrapper<SysFile>().eq("file_path", key).eq("file_location", 1).eq("del_flag", 0));
        for (SysFile file : records) {
            // MySQL collations can be case-insensitive while storage keys are not.
            if (!key.equals(file.getFilePath())) continue;
            if (user != null && user.getUsername().equals(file.getCreateBy())) return 200;
            for (TeachingWork work : works.selectList(new QueryWrapper<TeachingWork>().eq("del_flag", 0)
                    .and(q -> q.eq("work_file", file.getId()).or().eq("work_cover", file.getId())))) {
                try { access.requireCommunityWork(work); return 200; } catch (AuthorizationException denied) { }
            }
            // Prior versions stay private even when the current work has been published.
            if (user != null) for (Map<String,Object> row : jdbc.queryForList(
                    "SELECT h.data_id,h.data_content FROM sys_data_log h JOIN teaching_work w ON w.id=h.data_id "
                            + "WHERE h.data_table='teaching_work' AND w.del_flag=0 AND LOCATE(?,h.data_content)>0", file.getId())) {
                try {
                    JsonNode old = json.readTree(text(row,"data_content"));
                    if (old == null || !(file.getId().equals(old.path("workFile").asText()) || file.getId().equals(old.path("workCover").asText()))) continue;
                    access.requireReadWork(works.selectById(text(row,"data_id"))); return 200;
                } catch (java.io.IOException | AuthorizationException denied) { }
            }
            // A user-controlled avatar path cannot publish another uploader's private file.
            for (Map<String,Object> row : jdbc.queryForList("SELECT avatar FROM sys_user WHERE username=? AND del_flag=0", file.getCreateBy())) {
                if (references(text(row,"avatar"),key)) return 200;
            }
        }
        for (Map<String,Object> row : candidates("teaching_course", "course_icon,course_cover,course_map,course_desc", key)) {
            if (!live(row) || !any(row,key,"course_icon","course_cover","course_map","course_desc")) continue;
            if (one(row,"show_home") || course(text(row,"id"))) return 200;
        }
        if (user != null) {
            boolean student = user.getUserIdentity() == null || Integer.valueOf(1).equals(user.getUserIdentity());
            for (Map<String,Object> row : candidates("teaching_course_unit", "unit_cover,unit_intro,media_content,course_video,course_case,course_ppt,course_plan,course_work,course_work_answer", key)) {
                if (!live(row) || !course(text(row,"course_id"))) continue;
                if (any(row,key,"unit_cover","unit_intro","media_content","course_work","course_work_answer")) return 200;
                for (String field : Arrays.asList("course_video","course_case","course_ppt","course_plan")) {
                    if ((!student || one(row,"show_"+field)) && references(text(row,field),key)) return 200;
                }
            }
            for (Map<String,Object> row : candidates("teaching_additional_work", "work_cover,work_document_url,work_url,work_desc", key)) {
                if (!any(row,key,"work_cover","work_document_url","work_url","work_desc")) continue;
                Set<String> assigned = new HashSet<>(Arrays.asList(text(row,"work_dept").split(",")));
                if (!Collections.disjoint(assigned,access.managedDepartIds())) return 200;
                List<String> member = departments.userDepartIds(user.getId());
                if (one(row,"status") && member != null && !Collections.disjoint(assigned,member)) return 200;
            }
        }
        for (Map<String,Object> row : candidates("sys_config", "config_value", key)) {
            if (one(row,"config_enabled") && references(text(row,"config_value"),key)) return 200;
        }
        for (Map<String,Object> row : candidates("teaching_news", "news_content", key)) {
            Object state = row.get("news_status");
            if (state instanceof Number && ((Number) state).intValue() >= 1 && references(text(row,"news_content"),key)) return 200;
        }
        // No anonymous fallback for unregistered files, deleted records or unknown modules.
        return user == null ? 401 : 403;
    }

    private boolean course(String id) {
        if (access.currentUser() == null) return false;
        Integer live = jdbc.queryForObject("SELECT COUNT(*) FROM teaching_course WHERE id=? AND (del_flag=0 OR del_flag IS NULL)",Integer.class,id);
        if (live == null || live == 0) return false;
        try { access.requireCourse(id); return true; } catch (AuthorizationException denied) { return false; }
    }

    // Table/column arguments are constants above, never caller input. LOCATE only selects
    // candidates; authorization always requires an exact URL/key reference below. A URL can
    // encode any path character, using either hex case, so a single encoded key is not an
    // exhaustive prefilter. Include values containing '%' and let exact decode the URI once.
    private List<Map<String,Object>> candidates(String table,String columns,String key) {
        String expression = "CONCAT_WS(',',"+columns+")";
        return jdbc.queryForList("SELECT * FROM "+table+" WHERE LOCATE(?,"+expression+")>0 OR LOCATE(?,"+expression+")>0 OR LOCATE('%',"+expression+")>0",key,UriUtils.encodePath(key,"UTF-8"));
    }
    private boolean live(Map<String,Object> row) { return row.get("del_flag") == null || "0".equals(text(row,"del_flag")); }
    private boolean one(Map<String,Object> row,String field) { return "1".equals(text(row,field)) || Boolean.TRUE.equals(row.get(field)); }
    private String text(Map<String,Object> row,String field) { Object value=row.get(field);return value==null?"":value.toString(); }
    private boolean any(Map<String,Object> row,String key,String... fields) {
        for (String field:fields) if (references(text(row,field),key)) return true;
        return false;
    }
    private boolean references(String value,String key) {
        if (value == null || value.isEmpty()) return false;
        for (String part:value.split(",")) if (exact(part.trim(),key)) return true;
        Matcher links = HTML_LINK.matcher(value);
        while (links.find()) {
            String link=links.group(1)!=null?links.group(1):links.group(2)!=null?links.group(2):links.group(3);
            if (exact(HtmlUtils.htmlUnescape(link),key)) return true;
        }
        if (value.trim().startsWith("{") || value.trim().startsWith("[")) {
            try { return jsonReferences(json.readTree(value),key,0); } catch (java.io.IOException invalid) { return false; }
        }
        return false;
    }
    private boolean jsonReferences(JsonNode node,String key,int depth) {
        if (node == null || depth > 20) return false;
        if (node.isTextual()) return exact(node.asText(),key);
        if (node.isContainerNode()) for (JsonNode child:node) if (jsonReferences(child,key,depth+1)) return true;
        return false;
    }
    private boolean exact(String value,String key) {
        if (value.equals(key)) return true;
        String base=staticDomain.replaceAll("/+$","");
        try {
            URI reference=new URI(value);
            URI configured=new URI(base);
            // Absolute references must match the configured origin, not merely its path.
            if (!Objects.equals(reference.getScheme(),configured.getScheme())
                    || !Objects.equals(reference.getRawAuthority(),configured.getRawAuthority())) return false;
            // URI.getPath replaces malformed UTF-8 with U+FFFD. Reject it instead of
            // allowing invalid octets to identify a different, valid storage key.
            if (!validUtf8Escapes(reference.getRawPath())) return false;
            return Objects.equals(reference.getPath(),configured.getPath()+"/"+key);
        } catch (java.net.URISyntaxException invalid) { return false; }
    }

    private boolean validUtf8Escapes(String rawPath) {
        if (rawPath == null) return false;
        int index = rawPath.indexOf('%');
        if (index < 0) return true;
        byte[] octets = new byte[(rawPath.length()-index)/3];
        while (index >= 0) {
            int count = 0;
            // URI construction already validated every %HH escape. Validate each
            // contiguous octet run without decoding again or treating '+' as a space.
            do {
                octets[count++] = (byte) ((Character.digit(rawPath.charAt(index+1),16) << 4)
                        | Character.digit(rawPath.charAt(index+2),16));
                index += 3;
            } while (index < rawPath.length() && rawPath.charAt(index) == '%');
            try {
                StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)
                        .onUnmappableCharacter(CodingErrorAction.REPORT).decode(ByteBuffer.wrap(octets,0,count));
            } catch (CharacterCodingException invalid) {
                return false;
            }
            index = rawPath.indexOf('%',index);
        }
        return true;
    }
}
