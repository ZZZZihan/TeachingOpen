package org.jeecg.modules.teaching.service;

import org.jeecg.modules.teaching.mapper.PublicUserDirectoryMapper;
import org.jeecg.modules.teaching.vo.PublicUserDirectory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import java.util.stream.Collectors;

@Service
public class PublicUserDirectoryService {
    private final PublicUserDirectoryMapper mapper;
    public PublicUserDirectoryService(PublicUserDirectoryMapper mapper) { this.mapper = mapper; }

    @Transactional(readOnly = true)
    public PublicUserDirectory load(long requestedPage) {
        long total = mapper.countRegisteredUsers();
        long lastPage = Math.max(1, (total + 9) / 10);
        long page = Math.min(Math.max(1, requestedPage), lastPage);
        PublicUserDirectory result = new PublicUserDirectory();
        result.setTotal(total);
        result.setPageNo(page);
        result.setRecords(mapper.listRegisteredUsers((page - 1) * 10).stream().map(row -> {
            PublicUserDirectory.Entry entry = new PublicUserDirectory.Entry();
            entry.setName(maskName(row.getRealname()));
            entry.setSchool(row.getSchool() == null || row.getSchool().trim().isEmpty() ? "未填写" : row.getSchool().trim());
            entry.setIdentity("teacher".equals(row.getIdentity()) ? "教师" : "student".equals(row.getIdentity()) ? "学生" : "未填写");
            return entry;
        }).collect(Collectors.toList()));
        return result;
    }

    public static String maskName(String name) {
        if (name == null || name.trim().isEmpty()) return "*";
        int[] chars = name.trim().codePoints().toArray();
        if (chars.length == 1) return "*";
        StringBuilder masked = new StringBuilder().appendCodePoint(chars[0]);
        for (int i = 1; i < (chars.length == 2 ? 2 : chars.length - 1); i++) masked.append('*');
        if (chars.length > 2) masked.appendCodePoint(chars[chars.length - 1]);
        return masked.toString();
    }
}
