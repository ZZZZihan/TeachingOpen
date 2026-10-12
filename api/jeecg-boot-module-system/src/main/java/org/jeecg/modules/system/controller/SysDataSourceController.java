package org.jeecg.modules.system.controller;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import java.io.InputStream;
import java.util.*;
import java.util.stream.Collectors;
import javax.servlet.http.HttpServletRequest;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.modules.system.entity.SysDataSource;
import org.jeecg.modules.system.entity.SysDataSourceView;
import org.jeecg.modules.system.service.AccountAdministrationService;
import org.jeecg.modules.system.service.DataSourceAdministrationService;
import org.jeecg.modules.system.service.InfrastructureAccessService;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.jeecgframework.poi.excel.view.JeecgEntityExcelView;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;

/** Every management entry checks current dev membership before reads or import parsing. */
@RestController
@RequestMapping("/sys/dataSource")
public class SysDataSourceController {
    private final InfrastructureAccessService access;
    private final DataSourceAdministrationService administration;

    public SysDataSourceController(InfrastructureAccessService access, DataSourceAdministrationService administration) {
        this.access = access; this.administration = administration;
    }

    @GetMapping("/list")
    public Result<?> queryPageList(SysDataSource source,
            @RequestParam(defaultValue = "1") Integer pageNo,
            @RequestParam(defaultValue = "10") Integer pageSize, HttpServletRequest request) {
        access.requireOperator();
        IPage<SysDataSource> page = administration.page(new Page<>(pageNo, pageSize), query(source, request));
        return Result.ok(page.convert(SysDataSourceView::from));
    }

    @GetMapping("/options")
    public Result<?> queryOptions(SysDataSource source, HttpServletRequest request) {
        access.requireOperator();
        List<SysDataSource> values = administration.list(query(source, request));
        JSONArray options = new JSONArray(values.size());
        for (SysDataSource value : values) {
            JSONObject option = new JSONObject();
            option.put("value", value.getCode()); option.put("label", value.getName()); option.put("text", value.getName());
            options.add(option);
        }
        return Result.ok(options);
    }

    @PostMapping("/add")
    public Result<?> add(@RequestBody SysDataSource source) {
        access.requireOperator(); administration.add(source); return Result.ok("添加成功！");
    }

    @PutMapping("/edit")
    public Result<?> edit(@RequestBody SysDataSource source) {
        access.requireOperator(); administration.edit(source); return Result.ok("编辑成功！");
    }

    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam String id) {
        access.requireOperator(); administration.delete(Collections.singletonList(id)); return Result.ok("删除成功！");
    }

    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam String ids) {
        access.requireOperator(); administration.delete(AccountAdministrationService.ids(ids)); return Result.ok("批量删除成功！");
    }

    @GetMapping("/queryById")
    public Result<?> queryById(@RequestParam String id) {
        access.requireOperator(); return Result.ok(SysDataSourceView.from(administration.get(id)));
    }

    @RequestMapping("/exportXls")
    public ModelAndView exportXls(HttpServletRequest request, SysDataSource source) {
        access.requireOperator();
        List<SysDataSource> values = administration.list(query(source, request));
        String selection = request.getParameter("selections");
        if (selection != null && !selection.isEmpty()) {
            Set<String> selected = new HashSet<>(AccountAdministrationService.ids(selection));
            values = values.stream().filter(value -> selected.contains(value.getId())).collect(Collectors.toList());
        }
        ModelAndView view = new ModelAndView(new JeecgEntityExcelView());
        view.addObject(NormalExcelConstants.FILE_NAME, "多数据源管理");
        // The export schema has no password field, including when an entity contains a credential.
        view.addObject(NormalExcelConstants.CLASS, SysDataSourceView.class);
        view.addObject(NormalExcelConstants.PARAMS, new ExportParams("多数据源管理", "", "数据源"));
        view.addObject(NormalExcelConstants.DATA_LIST, values.stream().map(SysDataSourceView::from).collect(Collectors.toList()));
        return view;
    }

    @PostMapping("/importExcel")
    public Result<?> importExcel(HttpServletRequest request) throws Exception {
        access.requireOperator();
        if (!(request instanceof MultipartHttpServletRequest)) throw new JeecgBootException("请选择导入文件");
        List<SysDataSource> values = new ArrayList<>();
        ImportParams params = new ImportParams(); params.setTitleRows(2); params.setHeadRows(1);
        for (MultipartFile file : ((MultipartHttpServletRequest) request).getFileMap().values()) {
            try (InputStream input = file.getInputStream()) {
                values.addAll(ExcelImportUtil.importExcel(input, SysDataSource.class, params));
            }
        }
        administration.importSources(values);
        return Result.ok("导入成功，共" + values.size() + "条");
    }

    private QueryWrapper<SysDataSource> query(SysDataSource source, HttpServletRequest request) {
        // Passwords are write-only: do not allow a credential filter to become an oracle.
        source.setDbPassword(null);
        Map<String, String[]> parameters = new HashMap<>(request.getParameterMap());
        parameters.keySet().removeIf(key -> key.startsWith("dbPassword"));
        return QueryGenerator.initQueryWrapper(source, parameters);
    }

    @ExceptionHandler(UnauthorizedException.class)
    @ResponseStatus(HttpStatus.FORBIDDEN)
    public Result<?> denied(UnauthorizedException ignored) { return Result.error(403, "没有运维管理权限"); }
}
