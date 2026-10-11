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
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.*;

/** Resolve local bytes through current authoritative resource relationships on every request. */
@Service
public class LocalDownloadAccessService {
    @Autowired private ISysFileService files;
    @Autowired private TeachingWorkMapper works;
    @Autowired private TeachingAccessService access;
    @Autowired private ISysUserDepartService departments;
    @Autowired private JdbcTemplate jdbc;
    @Autowired private ObjectMapper json;
    @Autowired private LocalFileReferenceResolver references;
    @Autowired private LocalMediaReferenceIndex mediaIndex;

    public int status(String key) {
        LoginUser user = access.currentUser();
        if (user != null && access.isAdministrator()) return 200;
        Map<String, Boolean> courseAccess = new HashMap<>();
        List<SysFile> records = files.list(new QueryWrapper<SysFile>().eq("file_path", key).eq("file_location", 1).eq("del_flag", 0));
        Set<String> fileIds = new HashSet<>();
        Set<String> uploaders = new HashSet<>();
        for (SysFile file : records) {
            // MySQL collations can be case-insensitive while storage keys are not.
            if (!key.equals(file.getFilePath())) continue;
            if (user != null && user.getUsername().equals(file.getCreateBy())) return 200;
            fileIds.add(file.getId());
            uploaders.add(file.getCreateBy());
        }
        if (!fileIds.isEmpty()) {
            for (TeachingWork work : works.selectList(new QueryWrapper<TeachingWork>().eq("del_flag", 0)
                    .and(q -> q.in("work_file", fileIds).or().in("work_cover", fileIds)))) {
                // The SQL lookup may use a case-insensitive collation.
                if (!fileIds.contains(work.getWorkFile()) && !fileIds.contains(work.getWorkCover())) continue;
                try { access.requireCommunityWork(work); return 200; } catch (AuthorizationException denied) { }
            }
            // Prior versions stay private even when the current work has been published.
            if (user != null) {
                Set<String> historicWorks = new HashSet<>();
                for (Map<String,Object> row : mediaIndex.candidates("file", fileIds).getOrDefault(LocalMediaSource.HISTORY, Collections.emptyList())) {
                    if (!"teaching_work".equals(text(row, "data_table"))) continue;
                    try {
                        JsonNode old = json.readTree(text(row,"data_content"));
                        if (old != null && (fileIds.contains(old.path("workFile").asText()) || fileIds.contains(old.path("workCover").asText())))
                            historicWorks.add(text(row, "data_id"));
                    } catch (java.io.IOException denied) { }
                }
                if (!historicWorks.isEmpty()) for (TeachingWork work : works.selectBatchIds(historicWorks)) {
                    if (!historicWorks.contains(work.getId()) || !Integer.valueOf(0).equals(work.getDelFlag())) continue;
                    try { access.requireReadWork(work); return 200; } catch (AuthorizationException denied) { }
                }
            }
            // A user-controlled avatar path cannot publish another uploader's private file.
            for (Map<String,Object> row : jdbc.queryForList("SELECT username,avatar FROM sys_user WHERE username IN ("
                    + String.join(",", Collections.nCopies(uploaders.size(), "?")) + ") AND del_flag=0", uploaders.toArray())) {
                if (uploaders.contains(text(row, "username")) && references(text(row,"avatar"),key)) return 200;
            }
        }
        Map<LocalMediaSource, List<Map<String, Object>>> candidates = mediaIndex.candidates("key", Collections.singleton(key));
        for (Map<String,Object> row : candidates.getOrDefault(LocalMediaSource.COURSE, Collections.emptyList())) {
            if (!live(row) || !any(row,key,"course_icon","course_cover","course_map","course_desc")) continue;
            if (one(row,"show_home") || courseAccess.computeIfAbsent(text(row,"id"), this::course)) return 200;
        }
        if (user != null) {
            boolean student = user.getUserIdentity() == null || Integer.valueOf(1).equals(user.getUserIdentity());
            for (Map<String,Object> row : candidates.getOrDefault(LocalMediaSource.UNIT, Collections.emptyList())) {
                if (!live(row) || !courseAccess.computeIfAbsent(text(row,"course_id"), this::course)) continue;
                if (any(row,key,"unit_cover","unit_intro","media_content","course_work","course_work_answer")) return 200;
                for (String field : Arrays.asList("course_video","course_case","course_ppt","course_plan")) {
                    if ((!student || one(row,"show_"+field)) && references(text(row,field),key)) return 200;
                }
            }
            List<String> managed = null;
            List<String> member = null;
            for (Map<String,Object> row : candidates.getOrDefault(LocalMediaSource.ADDITIONAL, Collections.emptyList())) {
                if (!any(row,key,"work_cover","work_document_url","work_url","work_desc")) continue;
                Set<String> assigned = new HashSet<>(Arrays.asList(text(row,"work_dept").split(",")));
                if (managed == null) managed = access.managedDepartIds();
                if (!Collections.disjoint(assigned,managed)) return 200;
                if (member == null) member = departments.userDepartIds(user.getId());
                if (one(row,"status") && member != null && !Collections.disjoint(assigned,member)) return 200;
            }
        }
        for (Map<String,Object> row : candidates.getOrDefault(LocalMediaSource.CONFIG, Collections.emptyList())) {
            if (one(row,"config_enabled") && references(text(row,"config_value"),key)) return 200;
        }
        for (Map<String,Object> row : candidates.getOrDefault(LocalMediaSource.NEWS, Collections.emptyList())) {
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

    private boolean live(Map<String,Object> row) { return row.get("del_flag") == null || "0".equals(text(row,"del_flag")); }
    private boolean one(Map<String,Object> row,String field) { return "1".equals(text(row,field)) || Boolean.TRUE.equals(row.get(field)); }
    private String text(Map<String,Object> row,String field) { Object value=row.get(field);return value==null?"":value.toString(); }
    private boolean any(Map<String,Object> row,String key,String... fields) {
        for (String field:fields) if (references(text(row,field),key)) return true;
        return false;
    }
    private boolean references(String value,String key) {
        return references.resolve(value).keys().contains(key);
    }
}
