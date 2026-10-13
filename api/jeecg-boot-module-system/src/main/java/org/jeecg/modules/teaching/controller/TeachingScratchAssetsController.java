package org.jeecg.modules.teaching.controller;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import io.swagger.annotations.Api;
import lombok.extern.slf4j.Slf4j;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.aspect.annotation.AutoLog;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.base.controller.JeecgController;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.modules.system.service.GlobalResourceAccessService;
import org.jeecg.modules.teaching.entity.TeachingScratchAssets;
import org.jeecg.modules.teaching.service.ITeachingScratchAssetsService;
import org.jeecg.modules.teaching.service.ScratchAssetValidator;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import java.io.InputStream;
import java.util.*;

@Api(tags = "Scratch素材库")
@RestController
@RequestMapping("/teaching/teachingScratchAssets")
@Slf4j
public class TeachingScratchAssetsController extends JeecgController<TeachingScratchAssets, ITeachingScratchAssetsService> {
    @Autowired private ITeachingScratchAssetsService teachingScratchAssetsService;
    @Autowired private GlobalResourceAccessService access;

    /** Public editor library contract: valid rows survive malformed historical neighbours. */
    @GetMapping("/getScratchAssets")
    public JSONArray getScratchAssets(@RequestParam Integer assetType) {
        ScratchAssetValidator.type(assetType);
        JSONArray result = new JSONArray();
        List<TeachingScratchAssets> rows = teachingScratchAssetsService.list(new QueryWrapper<TeachingScratchAssets>()
                .eq("asset_type", assetType).eq("del_flag", 0));
        for (TeachingScratchAssets row : rows) {
            try {
                result.add(JSONObject.parseObject(ScratchAssetValidator.parse(assetType, row.getAssetData()).toString()));
            } catch (JeecgBootException invalid) {
                log.warn("Skipping invalid shared Scratch asset id={} type={}", row.getId(), assetType);
            }
        }
        return result;
    }

    @AutoLog(value = "Scratch素材库-分页列表查询")
    @GetMapping("/list")
    public Result<?> queryPageList(TeachingScratchAssets value,
            @RequestParam(name = "pageNo", defaultValue = "1") Integer pageNo,
            @RequestParam(name = "pageSize", defaultValue = "10") Integer pageSize, HttpServletRequest request) {
        access.requireAdministrator();
        return Result.ok(teachingScratchAssetsService.page(new Page<>(pageNo, pageSize),
                QueryGenerator.initQueryWrapper(value, request.getParameterMap())));
    }

    @AutoLog(value = "Scratch素材库-添加")
    @PostMapping("/add")
    public Result<?> add(@RequestBody TeachingScratchAssets value) {
        teachingScratchAssetsService.save(value); return Result.ok("添加成功！");
    }
    @AutoLog(value = "Scratch素材库-编辑")
    @PutMapping("/edit")
    public Result<?> edit(@RequestBody TeachingScratchAssets value) {
        teachingScratchAssetsService.updateById(value); return Result.ok("编辑成功！");
    }
    @AutoLog(value = "Scratch素材库-通过id删除")
    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam String id) {
        teachingScratchAssetsService.removeById(id); return Result.ok("删除成功！");
    }
    @AutoLog(value = "Scratch素材库-批量删除")
    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam String ids) {
        teachingScratchAssetsService.removeByIds(Arrays.asList(ids.split(",", -1))); return Result.ok("批量删除成功！");
    }
    @AutoLog(value = "Scratch素材库-通过id查询")
    @GetMapping("/queryById")
    public Result<?> queryById(@RequestParam String id) {
        access.requireAdministrator();
        return Result.ok(teachingScratchAssetsService.getById(ScratchAssetValidator.id(id)));
    }
    @RequestMapping("/exportXls")
    public ModelAndView exportXls(HttpServletRequest request, TeachingScratchAssets value) {
        access.requireAdministrator();
        return super.exportXls(request, value, TeachingScratchAssets.class, "Scratch素材库");
    }

    @PostMapping("/importExcel")
    public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) {
        access.requireAdministrator();
        if (!(request instanceof MultipartHttpServletRequest)) return Result.error("请上传素材表格");
        List<TeachingScratchAssets> rows = new ArrayList<>();
        ImportParams params = new ImportParams(); params.setTitleRows(2); params.setHeadRows(1); params.setNeedSave(false);
        for (MultipartFile file : ((MultipartHttpServletRequest) request).getFileMap().values()) {
            if (file.getSize() > 2097152) return Result.error("素材表格过大");
            try (InputStream input = file.getInputStream()) {
                rows.addAll(ExcelImportUtil.importExcel(input, TeachingScratchAssets.class, params));
            } catch (Exception failure) { return Result.error("素材表格格式不正确"); }
            if (rows.size() > 200) return Result.error("一次最多导入200条素材");
        }
        teachingScratchAssetsService.saveBatch(rows);
        return Result.ok("文件导入成功！数据行数：" + rows.size());
    }
}
