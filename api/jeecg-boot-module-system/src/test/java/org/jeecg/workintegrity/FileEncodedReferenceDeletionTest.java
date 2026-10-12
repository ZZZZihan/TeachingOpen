package org.jeecg.workintegrity;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.ibatis.builder.xml.XMLMapperBuilder;
import org.apache.ibatis.mapping.Environment;
import org.apache.ibatis.session.Configuration;
import org.apache.ibatis.session.SqlSession;
import org.apache.ibatis.session.SqlSessionFactoryBuilder;
import org.apache.ibatis.transaction.jdbc.JdbcTransactionFactory;
import org.h2.jdbcx.JdbcDataSource;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.mapper.SysFileMapper;
import org.jeecg.modules.system.service.*;
import org.jeecg.modules.system.service.impl.SysFileServiceImpl;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.junit.After;
import org.junit.Before;
import org.junit.Test;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.util.ReflectionUtils;

import java.io.InputStream;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import static org.junit.Assert.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

/** Execute the production MyBatis reference SQL and parser against real rows.
 * Encoded fixtures intentionally contain neither the raw key nor the file ID. */
public class FileEncodedReferenceDeletionTest {
    private static final String DOMAIN = "/api/sys/common/static";
    private JdbcTemplate jdbc;
    private SqlSession session;
    private SysFileMapper mapper;
    private SysFileServiceImpl files;
    private LocalFileReferenceResolver resolver;
    private SysFile file;

    @Before public void setup() throws Exception {
        JdbcDataSource data = new JdbcDataSource();
        data.setURL("jdbc:h2:mem:encoded_" + UUID.randomUUID() + ";MODE=MySQL;DB_CLOSE_DELAY=-1");
        jdbc = new JdbcTemplate(data);
        jdbc.execute("CREATE TABLE sys_file(id VARCHAR(64),file_path VARCHAR(255),file_location INT)");
        jdbc.execute("CREATE TABLE teaching_work(id VARCHAR(64),work_file VARCHAR(64),work_cover VARCHAR(64))");
        jdbc.execute("CREATE TABLE teaching_course(id VARCHAR(64),course_icon LONGTEXT,course_cover LONGTEXT,course_map LONGTEXT,course_desc LONGTEXT)");
        jdbc.execute("CREATE TABLE teaching_course_unit(id VARCHAR(64),unit_cover LONGTEXT,course_video LONGTEXT,course_case LONGTEXT,course_ppt LONGTEXT,course_work LONGTEXT,course_work_answer LONGTEXT,course_plan LONGTEXT,unit_intro LONGTEXT,media_content LONGTEXT)");
        jdbc.execute("CREATE TABLE teaching_additional_work(id VARCHAR(64),work_cover LONGTEXT,work_document_url LONGTEXT,work_url LONGTEXT,work_desc LONGTEXT,work_dept VARCHAR(64),status INT)");
        jdbc.execute("CREATE TABLE sys_data_log(id VARCHAR(64),data_id VARCHAR(64),data_table VARCHAR(64),data_content LONGTEXT)");
        jdbc.execute("CREATE TABLE sys_user(avatar LONGTEXT)");
        jdbc.execute("CREATE TABLE sys_config(id VARCHAR(64),config_value LONGTEXT)");
        jdbc.execute("CREATE TABLE teaching_news(id VARCHAR(64),news_content LONGTEXT)");
        jdbc.execute("CREATE TABLE teaching_scratch_assets(asset_data LONGTEXT,md5_ext LONGTEXT)");
        jdbc.execute("CREATE TABLE teaching_course_media(media_path LONGTEXT)");
        jdbc.update("INSERT INTO teaching_additional_work(id,work_dept,status) VALUES('task-a','class-a',1)");
        Configuration config = new Configuration(new Environment("test", new JdbcTransactionFactory(), data));
        String resource = "org/jeecg/modules/system/mapper/xml/SysFileMapper.xml";
        try (InputStream input = getClass().getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(input);
            new XMLMapperBuilder(input, config, resource, config.getSqlFragments()).parse();
        }
        session = new SqlSessionFactoryBuilder().build(config).openSession(true);
        mapper = mock(SysFileMapper.class, org.mockito.AdditionalAnswers.delegatesTo(session.getMapper(SysFileMapper.class)));
        // H2 has an upper-case INFORMATION_SCHEMA; the application detection SQL
        // is independently exercised against MySQL by the HTTP fixture.
        doReturn(0).when(mapper).hasCourseMediaTable();
        files = new SysFileServiceImpl();
        ReflectionTestUtils.setField(files, "baseMapper", mapper);
        resolver = new LocalFileReferenceResolver();
        ReflectionTestUtils.setField(resolver, "json", new ObjectMapper());
        ReflectionTestUtils.setField(resolver, "staticDomain", DOMAIN);
        // The same test also runs before the deletion service adopts the parser.
        if (ReflectionUtils.findField(SysFileServiceImpl.class, "references") != null)
            ReflectionTestUtils.setField(files, "references", resolver);
        file = new SysFile().setId("unrelated-file-id").setFilePath("private.txt").setFileLocation(1).setDelFlag(0);
    }

    @After public void close() { if (session != null) session.close(); }

    private String percent() { return DOMAIN + "/%70rivate.txt"; }
    private String entity() { return "<img src='" + DOMAIN + "/&#112;rivate.txt'>"; }
    private String json() { return "{\"media\":[{\"src\":\"" + DOMAIN.replace("/", "\\/") + "/" + "\\u0070rivate.txt\"}]}"; }

    private void references(String value) {
        assertFalse(value.contains(file.getFilePath()));
        assertFalse(value.contains(file.getId()));
        assertTrue("shared parser must resolve fixture", resolver.resolve(value).keys().contains(file.getFilePath()));
        jdbc.update("UPDATE teaching_additional_work SET work_desc=? WHERE id='task-a'", value);
        session.clearCache();
        assertEquals("raw-only scan is insufficient", 0, mapper.referenceCount(file));
        assertTrue("encoded live reference must prevent deletion", files.isReferenced(file));
    }

    @Test public void percentEncodedUrlPreventsDeletion() { references(percent()); }
    @Test public void htmlEntityReferencePreventsDeletion() { references(entity()); }
    @Test public void nestedJsonUnicodeAndSlashEscapesPreventDeletion() { references(json()); }
    @Test public void htmlHexEntityAndPercentCombinationPreventsDeletion() {
        references("<a href='" + DOMAIN + "/&#x25;70rivate.txt'>read</a>");
    }
    @Test public void independentJsonFieldsAreNotConcatenatedBeforeParsing() {
        jdbc.update("UPDATE teaching_additional_work SET work_url='[\"https://external.example/test\"]'");
        references(json());
    }
    @Test public void everyExistingReferenceFamilyUsesTheSameDecode() {
        String[][] fields = {{"teaching_course", "course_desc"}, {"teaching_course_unit", "media_content"},
                {"sys_user", "avatar"}, {"sys_config", "config_value"}, {"teaching_news", "news_content"},
                {"teaching_scratch_assets", "asset_data"}};
        for (String[] field : fields) {
            jdbc.update("INSERT INTO " + field[0] + "(" + field[1] + ") VALUES(?)", json());
            session.clearCache();
            assertTrue(field[0], files.isReferenced(file));
            jdbc.update("DELETE FROM " + field[0]);
        }
    }
    @Test public void optionalCourseMediaAndExistingWorkHistoryAreProtected() {
        doReturn(1).when(mapper).hasCourseMediaTable();
        jdbc.update("INSERT INTO teaching_course_media VALUES(?)", percent());
        assertTrue(files.isReferenced(file));
        jdbc.update("DELETE FROM teaching_course_media");
        jdbc.update("INSERT INTO teaching_work(id) VALUES('historical-work')");
        jdbc.update("INSERT INTO sys_data_log(data_id,data_table,data_content) VALUES('historical-work','teaching_work',?)", json());
        session.clearCache();
        assertTrue(files.isReferenced(file));
    }
    @Test public void encodedExternalUrlAndDoubleEncodingDoNotCountAsExactLocalReference() {
        jdbc.update("UPDATE teaching_additional_work SET work_desc=?", "https://external.example/static/%70rivate.txt");
        assertFalse(files.isReferenced(file));
        jdbc.update("UPDATE teaching_additional_work SET work_desc=?", DOMAIN + "/%2570rivate.txt");
        session.clearCache();
        assertFalse(files.isReferenced(file));
    }
    @Test public void ordinaryReferenceAndCloudBehaviorStayConservative() {
        jdbc.update("UPDATE teaching_additional_work SET work_desc=?", "https://cdn.example/private.txt");
        assertTrue(files.isReferenced(file));
        file.setFileLocation(2);
        assertTrue(files.isReferenced(file));
        verify(mapper, never()).encodedReferenceCandidates();
    }
    @Test public void entityAndJsonStudentDownloadsUseTheSameCandidateSemantics() {
        jdbc.execute("CREATE TABLE sys_local_file_reference(source_type VARCHAR(64) NOT NULL,source_id VARCHAR(64) NOT NULL,"
                + "field_name VARCHAR(64) NOT NULL,reference_kind VARCHAR(8) NOT NULL,reference_hash CHAR(64) NOT NULL,"
                + "reference_value VARCHAR(1024) NOT NULL,PRIMARY KEY(source_type,source_id,field_name,reference_kind,reference_hash))");
        jdbc.execute("CREATE TABLE sys_local_file_reference_state(id INT PRIMARY KEY,version INT NOT NULL,static_domain VARCHAR(1024))");
        jdbc.update("INSERT INTO sys_local_file_reference_state(id,version) VALUES(1,0)");
        LocalMediaReferenceIndex index = new LocalMediaReferenceIndex();
        ReflectionTestUtils.setField(index,"jdbc",jdbc);
        ReflectionTestUtils.setField(index,"json",new ObjectMapper());
        ReflectionTestUtils.setField(index,"resolver",resolver);
        ReflectionTestUtils.setField(index,"transactionManager",new DataSourceTransactionManager(jdbc.getDataSource()));
        ReflectionTestUtils.setField(index,"staticDomain",DOMAIN);
        index.initialize();
        assertEquals(Integer.valueOf(1),jdbc.queryForObject("SELECT version FROM sys_local_file_reference_state WHERE id=1",Integer.class));
        assertEquals(DOMAIN,jdbc.queryForObject("SELECT static_domain FROM sys_local_file_reference_state WHERE id=1",String.class));
        LocalDownloadAccessService downloads = new LocalDownloadAccessService();
        ISysFileService records = mock(ISysFileService.class);
        TeachingAccessService access = mock(TeachingAccessService.class);
        ISysUserDepartService departments = mock(ISysUserDepartService.class);
        LoginUser student = new LoginUser(); student.setId("student-a"); student.setUsername("student-a");
        when(access.currentUser()).thenReturn(student);
        when(departments.userDepartIds("student-a")).thenReturn(Collections.singletonList("class-a"));
        ReflectionTestUtils.setField(downloads, "files", records);
        ReflectionTestUtils.setField(downloads, "works", mock(TeachingWorkMapper.class));
        ReflectionTestUtils.setField(downloads, "access", access);
        ReflectionTestUtils.setField(downloads, "departments", departments);
        ReflectionTestUtils.setField(downloads, "jdbc", jdbc);
        ReflectionTestUtils.setField(downloads, "json", new ObjectMapper());
        ReflectionTestUtils.setField(downloads, "references", resolver);
        ReflectionTestUtils.setField(downloads, "mediaIndex", index);
        for (String value : new String[]{percent(), entity(), json()}) {
            jdbc.update("UPDATE teaching_additional_work SET work_desc=?", value);
            index.rebuild(true);
            assertEquals("candidate must belong to the assigned work",Integer.valueOf(1),jdbc.queryForObject(
                    "SELECT COUNT(*) FROM sys_local_file_reference WHERE source_type='teaching_additional_work' AND source_id='task-a'"
                            + " AND field_name='work_desc' AND reference_kind='key' AND reference_hash=? AND reference_value=?",
                    Integer.class,LocalMediaReferenceIndex.hash(file.getFilePath()),file.getFilePath()));
            List<Map<String,Object>> indexed = jdbc.queryForList("SELECT * FROM sys_local_file_reference ORDER BY reference_hash");
            assertEquals("assigned student can read encoded attachment", 200, downloads.status(file.getFilePath()));
            when(departments.userDepartIds("student-a")).thenReturn(Collections.singletonList("class-b"));
            assertEquals("exact decoding does not bypass assignment scope", 403, downloads.status(file.getFilePath()));
            assertEquals("denied read must preserve every indexed reference",indexed,
                    jdbc.queryForList("SELECT * FROM sys_local_file_reference ORDER BY reference_hash"));
            when(departments.userDepartIds("student-a")).thenReturn(Collections.singletonList("class-a"));
        }
    }
}
