package org.jeecg.modules.system.service;

import java.io.InputStream;
import java.util.*;
import javax.servlet.http.HttpServletRequest;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;

/** Parse all import files before invoking a single authorized transactional saveBatch. */
public final class GlobalResourceImport {
    private GlobalResourceImport() { }
    public static <T> List<T> read(HttpServletRequest request, Class<T> type) {
        if (!(request instanceof MultipartHttpServletRequest)) throw new JeecgBootException("请上传表格");
        ImportParams params = new ImportParams(); params.setTitleRows(2); params.setHeadRows(1); params.setNeedSave(false);
        List<T> rows = new ArrayList<>();
        for (MultipartFile file : ((MultipartHttpServletRequest)request).getFileMap().values()) {
            if (file.getSize() > 2097152) throw new JeecgBootException("表格过大");
            try (InputStream input = file.getInputStream()) { rows.addAll(ExcelImportUtil.importExcel(input, type, params)); }
            catch (Exception failure) { throw new JeecgBootException("表格格式不正确"); }
            if (rows.size() > 200) throw new JeecgBootException("一次最多导入200条数据");
        }
        if (rows.isEmpty()) throw new JeecgBootException("表格没有数据");
        return rows;
    }
}
