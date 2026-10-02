package org.jeecg.modules.system.controller;

import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;
import org.jeecg.common.api.vo.Result;
import org.jeecg.modules.system.entity.SysFile;
import org.jeecg.modules.system.service.ISysFileService;
import org.jeecg.modules.system.service.FileAccessService;
import org.jeecg.common.exception.JeecgBootException;
import org.apache.shiro.authz.annotation.RequiresRoles;
import org.apache.shiro.authz.annotation.Logical;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import lombok.extern.slf4j.Slf4j;

import org.jeecg.common.system.base.controller.JeecgController;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.ModelAndView;
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import org.jeecg.common.aspect.annotation.AutoLog;

 /**
 * @Description: 文件管理
 * @Author: jeecg-boot
 * @Date:   2020-04-11
 * @Version: V1.0
 */
@Api(tags="文件管理")
@RestController
@RequestMapping("/system/sysFile")
@Slf4j
public class SysFileController extends JeecgController<SysFile, ISysFileService> {
	@Autowired
	private ISysFileService sysFileService;
	@Autowired private FileAccessService fileAccess;

	/**
	 * 分页列表查询
	 *
	 * @param sysFile
	 * @param pageNo
	 * @param pageSize
	 * @param req
	 * @return
	 */
	@AutoLog(value = "文件管理-分页列表查询")
	@ApiOperation(value="文件管理-分页列表查询", notes="文件管理-分页列表查询")
	@GetMapping(value = "/list")
	public Result<?> queryPageList(SysFile sysFile,
								   @RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
								   @RequestParam(name="pageSize", defaultValue="10") Integer pageSize,
								   HttpServletRequest req) {
		QueryWrapper<SysFile> queryWrapper = new QueryWrapper<>();
        // Do not let advanced client query/sort parameters widen the ownership scope.
        queryWrapper.eq("del_flag", 0);
        if (!fileAccess.administrator()) queryWrapper.eq("create_by", fileAccess.user().getUsername());
        if (sysFile.getFileName() != null) queryWrapper.like("file_name", sysFile.getFileName());
        if (sysFile.getFileTag() != null) queryWrapper.eq("file_tag", sysFile.getFileTag());
        if (sysFile.getFileType() != null) queryWrapper.eq("file_type", sysFile.getFileType());
        if (sysFile.getFileLocation() != null) queryWrapper.eq("file_location", sysFile.getFileLocation());
        queryWrapper.orderByDesc("create_time").orderByAsc("id");
        Page<SysFile> page = new Page<SysFile>(Math.max(1, pageNo), Math.min(100, Math.max(1, pageSize)));
		IPage<SysFile> pageList = sysFileService.page(page, queryWrapper);
		return Result.ok(pageList);
	}
	
	/**
	 *   添加
	 *
	 * @param sysFile
	 * @return
	 */
	@AutoLog(value = "文件管理-添加")
	@ApiOperation(value="文件管理-添加", notes="文件管理-添加")
	@PostMapping(value = "/add")
	public Result<?> add(@RequestBody SysFile sysFile) {
		return Result.ok(fileAccess.register(sysFile));
	}
	
	/**
	 *  编辑
	 *
	 * @param sysFile
	 * @return
	 */
	@AutoLog(value = "文件管理-编辑")
	@ApiOperation(value="文件管理-编辑", notes="文件管理-编辑")
	@PutMapping(value = "/edit")
	public Result<?> edit(@RequestBody SysFile sysFile) {
		fileAccess.updateDisplay(sysFileService.getById(sysFile.getId()), sysFile);
		return Result.ok("编辑成功!");
	}
	
	/**
	 *   通过id删除
	 *
	 * @param id
	 * @return
	 */
	@AutoLog(value = "文件管理-通过id删除")
	@ApiOperation(value="文件管理-通过id删除", notes="文件管理-通过id删除")
	@DeleteMapping(value = "/delete")
	public Result<?> delete(@RequestParam(name="id",required=true) String id) {
		fileAccess.requireDeletion(sysFileService.getById(id));
        return sysFileService.deleteWithFile(id) ? Result.ok("删除成功!") : Result.error("文件删除失败，请稍后重试");
	}

	 /**
	  *   通过filePath删除
	  *
	  * @param filePath
	  * @return
	  */
	 @AutoLog(value = "文件管理-通过filePath删除")
	 @ApiOperation(value="文件管理-通过filePath删除", notes="文件管理-通过filePath删除")
	 @DeleteMapping(value = "/deleteByPath")
	 public Result<?> deleteByPath(@RequestParam(name="filePath",required=true) String filePath) {
		 List<SysFile> matches = sysFileService.list(new QueryWrapper<SysFile>().eq("file_path", filePath));
         if (matches.size() != 1) throw new JeecgBootException("文件不存在或路径不唯一");
         return delete(matches.get(0).getId());
	 }
	
	/**
	 *  批量删除
	 *
	 * @param ids
	 * @return
	 */
	@AutoLog(value = "文件管理-批量删除")
	@ApiOperation(value="文件管理-批量删除", notes="文件管理-批量删除")
	@DeleteMapping(value = "/deleteBatch")
	public Result<?> deleteBatch(@RequestParam(name="ids",required=true) String ids) {
		List<String> idList = Arrays.stream(ids.split(",", -1)).map(String::trim).distinct().collect(Collectors.toList());
        if (idList.size() > 100 || idList.contains("")) throw new JeecgBootException("请选择 1 至 100 个文件");
        // Authorize the entire batch before deleting any bytes.
        for (String id : idList) fileAccess.requireDeletion(sysFileService.getById(id));
        int deleted = 0;
        for (String id : idList) {
            if (!sysFileService.deleteWithFile(id)) return Result.error("已删除 " + deleted + " 个文件，其余未删除，请刷新后重试");
            deleted++;
        }
        return Result.ok("批量删除成功!");
	}
	
	/**
	 * 通过id查询
	 *
	 * @param id
	 * @return
	 */
	@AutoLog(value = "文件管理-通过id查询")
	@ApiOperation(value="文件管理-通过id查询", notes="文件管理-通过id查询")
	@GetMapping(value = "/queryById")
	public Result<?> queryById(@RequestParam(name="id",required=true) String id) {
		SysFile sysFile = sysFileService.getById(id);
		fileAccess.requireRead(sysFile);
		return Result.ok(sysFile);
	}

    /**
    * 导出excel
    *
    * @param request
    * @param sysFile
    */
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    @RequestMapping(value = "/exportXls")
    public ModelAndView exportXls(HttpServletRequest request, SysFile sysFile) {
        return super.exportXls(request, sysFile, SysFile.class, "文件管理");
    }

    /**
      * 通过excel导入数据
    *
    * @param request
    * @param response
    * @return
    */
    @RequiresRoles(value = {"admin", "dev"}, logical = Logical.OR)
    @RequestMapping(value = "/importExcel", method = RequestMethod.POST)
    public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) {
        return super.importExcel(request, response, SysFile.class);
    }

}
