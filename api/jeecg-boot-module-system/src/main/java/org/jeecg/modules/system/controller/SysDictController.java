package org.jeecg.modules.system.controller;


import java.io.InputStream;
import java.util.*;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

import cn.hutool.crypto.SecureUtil;
import com.baomidou.mybatisplus.core.conditions.update.UpdateWrapper;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.apache.shiro.authz.annotation.RequiresRoles;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CacheConstant;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.query.QueryGenerator;
import org.jeecg.common.system.vo.DictModel;
import org.jeecg.common.system.vo.DictQuery;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.ImportExcelUtil;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.shiro.vo.DefContants;
import org.jeecg.modules.system.entity.SysDict;
import org.jeecg.modules.system.entity.SysDictItem;
import org.jeecg.modules.system.model.SysDictTree;
import org.jeecg.modules.system.model.TreeSelectModel;
import org.jeecg.modules.system.service.ISysDictItemService;
import org.jeecg.modules.system.service.ISysDictService;
import org.jeecg.modules.system.service.NamedTableDictionaryService;
import org.jeecg.modules.system.vo.SysDictPage;
import org.jeecgframework.poi.excel.ExcelImportUtil;
import org.jeecgframework.poi.excel.def.NormalExcelConstants;
import org.jeecgframework.poi.excel.entity.ExportParams;
import org.jeecgframework.poi.excel.entity.ImportParams;
import org.jeecgframework.poi.excel.view.JeecgEntityExcelView;
import org.springframework.beans.BeanUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.multipart.MultipartHttpServletRequest;
import org.springframework.web.servlet.ModelAndView;

import com.alibaba.fastjson.JSON;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.core.metadata.IPage;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

import lombok.extern.slf4j.Slf4j;

/**
 * <p>
 * 字典表 前端控制器
 * </p>
 *
 * @Author zhangweijian
 * @since 2018-12-28
 */
@RestController
@RequestMapping("/sys/dict")
@Slf4j
public class SysDictController {

	@Autowired
	private ISysDictService sysDictService;
	@Autowired
	private NamedTableDictionaryService namedTableDictionaries;
	@Autowired
	private ISysDictItemService sysDictItemService;
	@Autowired
	public RedisTemplate<String, Object> redisTemplate;

	@RequestMapping("getByCode")
	public Result<SysDict> getByCode(@RequestParam String dicCode){
		Result<SysDict> result = new Result<>();
		result.setResult(sysDictService.getOne(new QueryWrapper<SysDict>().eq("dict_code", dicCode)));
		return result;
	}

	@RequestMapping(value = "/list", method = RequestMethod.GET)
	public Result<IPage<SysDict>> queryPageList(SysDict sysDict,@RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
									  @RequestParam(name="pageSize", defaultValue="10") Integer pageSize,HttpServletRequest req) {
		Result<IPage<SysDict>> result = new Result<IPage<SysDict>>();
		QueryWrapper<SysDict> queryWrapper = QueryGenerator.initQueryWrapper(sysDict, req.getParameterMap());
		Page<SysDict> page = new Page<SysDict>(pageNo, pageSize);
		IPage<SysDict> pageList = sysDictService.page(page, queryWrapper);
		log.debug("查询当前页："+pageList.getCurrent());
		log.debug("查询当前页数量："+pageList.getSize());
		log.debug("查询结果数量："+pageList.getRecords().size());
		log.debug("数据总数："+pageList.getTotal());
		result.setSuccess(true);
		result.setResult(pageList);
		return result;
	}

	/**
	 * @功能：获取树形字典数据
	 * @param sysDict
	 * @param pageNo
	 * @param pageSize
	 * @param req
	 * @return
	 */
	@SuppressWarnings("unchecked")
	@RequestMapping(value = "/treeList", method = RequestMethod.GET)
	public Result<List<SysDictTree>> treeList(SysDict sysDict,@RequestParam(name="pageNo", defaultValue="1") Integer pageNo,
									  @RequestParam(name="pageSize", defaultValue="10") Integer pageSize,HttpServletRequest req) {
		Result<List<SysDictTree>> result = new Result<>();
		LambdaQueryWrapper<SysDict> query = new LambdaQueryWrapper<>();
		// 构造查询条件
		String dictName = sysDict.getDictName();
		if(oConvertUtils.isNotEmpty(dictName)) {
			query.like(true, SysDict::getDictName, dictName);
		}
		query.orderByDesc(true, SysDict::getCreateTime);
		List<SysDict> list = sysDictService.list(query);
		List<SysDictTree> treeList = new ArrayList<>();
		for (SysDict node : list) {
			treeList.add(new SysDictTree(node));
		}
		result.setSuccess(true);
		result.setResult(treeList);
		return result;
	}

	/**
	 * 获取字典数据
	 * @param dictCode 字典code
	 * @param dictCode 标量字典名称或服务器登记的固定用途；旧三元组仅精确兼容
	 * @return
	 */
	@RequestMapping(value = "/getDictItems/{dictCode}", method = RequestMethod.GET)
	public Result<List<DictModel>> getDictItems(@PathVariable String dictCode, @RequestParam(value = "sign",required = false) String sign,HttpServletRequest request) {
        try {
            List<DictModel> items;
            if (namedTableDictionaries.isTablePurpose(dictCode)) {
                items = namedTableDictionaries.items(dictCode);
            } else {
                namedTableDictionaries.validateScalarCode(dictCode);
                items = sysDictService.queryDictItemsByCode(dictCode);
            }
            Result<List<DictModel>> result = new Result<>();
            result.setResult(items);
            return result;
        } catch (Exception e) {
            return dictionaryFailure(e);
        }
	}

	/**
	 * 获取全部字典数据
	 *
	 * @return
	 */
	@RequestMapping(value = "/queryAllDictItems", method = RequestMethod.GET)
	public Result<?> queryAllDictItems(HttpServletRequest request) {
		Map<String, List<DictModel>> res = new HashMap<String, List<DictModel>>();
		res = sysDictService.queryAllDictItems();
		return Result.ok(res);
	}

	/**
	 * 获取字典数据
	 * @param dictCode
	 * @return
	 */
	@RequestMapping(value = "/getDictText/{dictCode}/{key}", method = RequestMethod.GET)
	public Result<String> getDictText(@PathVariable("dictCode") String dictCode, @PathVariable("key") String key) {
		log.info(" dictCode : "+ dictCode);
		Result<String> result = new Result<String>();
		String text = null;
		try {
			text = sysDictService.queryDictTextByKey(dictCode, key);
			 result.setSuccess(true);
			 result.setResult(text);
		} catch (Exception e) {
			log.error(e.getMessage(),e);
			result.error500("操作失败");
			return result;
		}
		return result;
	}

	/**
	 * 大数据量的字典表 走异步加载  即前端输入内容过滤数据
	 * @param dictCode
	 * @return
	 */
	@RequestMapping(value = "/loadDict/{dictCode}", method = RequestMethod.GET)
	public Result<List<DictModel>> loadDict(@PathVariable String dictCode,@RequestParam(name="keyword") String keyword, @RequestParam(value = "sign",required = false) String sign,HttpServletRequest request) {
        try {
            Result<List<DictModel>> result = new Result<>();
            result.setResult(namedTableDictionaries.search(dictCode, keyword));
            return result;
        } catch (Exception e) {
            return dictionaryFailure(e);
        }
	}

	/**
	 * 根据字典code加载字典text 返回
	 */
	@RequestMapping(value = "/loadDictItem/{dictCode}", method = RequestMethod.GET)
	public Result<List<String>> loadDictItem(@PathVariable String dictCode,@RequestParam(name="key") String key, @RequestParam(value = "sign",required = false) String sign,HttpServletRequest request) {
        try {
            Result<List<String>> result = new Result<>();
            result.setResult(namedTableDictionaries.labels(dictCode, key));
            return result;
        } catch (Exception e) {
            return dictionaryFailure(e);
        }
	}

	/**
	 * 按固定分类/菜单用途加载树形数据，不接受自定义表、字段或过滤条件
	 */
    @RequestMapping(value = "/loadTreeData", method = RequestMethod.GET)
    public Result<List<TreeSelectModel>> loadTreeData(@RequestParam(name="pid", defaultValue="") String pid,
            @RequestParam(name="dictCode", required=false) String dictCode,
            @RequestParam(name="pidField", required=false) String pidField,
            @RequestParam(name="tableName", required=false) String tableName,
            @RequestParam(name="text", required=false) String text,
            @RequestParam(name="code", required=false) String code,
            @RequestParam(name="hasChildField", required=false) String hasChildField,
            @RequestParam(name="condition", required=false) String condition,
            @RequestParam(value="sign", required=false) String sign, HttpServletRequest request) {
        try {
            String purpose = dictCode;
            if (purpose == null) {
                purpose = tableName + "," + text + "," + code;
            } else if (tableName != null || text != null || code != null) {
                throw new IllegalArgumentException("字典用途参数不能与表字段混用");
            }
            Result<List<TreeSelectModel>> result = new Result<>();
            result.setResult(namedTableDictionaries.tree(purpose, pid, pidField, hasChildField, condition));
            return result;
        } catch (Exception e) {
            return dictionaryFailure(e);
        }
    }

	/**
	 * 【APP接口】根据字典配置查询表字典数据
	 * @param query
	 * @param pageNo
	 * @param pageSize
	 * @return
	 */
	@GetMapping("/queryTableData")
	public Result<List<DictModel>> queryTableData(DictQuery query,
												  @RequestParam(name = "pageNo", defaultValue = "1") Integer pageNo,
												  @RequestParam(name = "pageSize", defaultValue = "10") Integer pageSize,
												  @RequestParam(value = "sign",required = false) String sign,HttpServletRequest request){
        return dictionaryFailure(new IllegalArgumentException("通用表查询已停用，请使用已配置的字典用途"));
	}

    private <T> Result<T> dictionaryFailure(Exception exception) {
        Result<T> result = new Result<>();
        result.setSuccess(false);
        if (exception instanceof UnauthorizedException) {
            result.setCode(403);
            result.setMessage("无字典访问权限");
        } else if (exception instanceof IllegalArgumentException) {
            result.setCode(400);
            result.setMessage(exception.getMessage());
        } else {
            result.setCode(500);
            result.setMessage("字典读取失败，请稍后重试");
            log.error("字典读取失败", exception);
        }
        return result;
    }

	/**
	 * @功能：新增
	 * @param sysDict
	 * @return
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/add", method = RequestMethod.POST)
	public Result<SysDict> add(@RequestBody SysDict sysDict) {
		Result<SysDict> result = new Result<SysDict>();
		try {
			sysDict.setCreateTime(new Date());
			sysDict.setDelFlag(CommonConstant.DEL_FLAG_0);
			sysDictService.save(sysDict);
			result.success("保存成功！");
		} catch (Exception e) {
			log.error(e.getMessage(),e);
			result.error500("操作失败");
		}
		return result;
	}

	/**
	 * @功能：编辑
	 * @param sysDict
	 * @return
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/edit", method = RequestMethod.PUT)
	public Result<SysDict> edit(@RequestBody SysDict sysDict) {
		Result<SysDict> result = new Result<SysDict>();
		SysDict sysdict = sysDictService.getById(sysDict.getId());
		if(sysdict==null) {
			result.error500("未找到对应实体");
		}else {
			sysDict.setUpdateTime(new Date());
			boolean ok = sysDictService.updateById(sysDict);
			if(ok) {
				result.success("编辑成功!");
			}
		}
		return result;
	}

	/**
	 * @功能：删除
	 * @param id
	 * @return
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/delete", method = RequestMethod.DELETE)
	@CacheEvict(value=CacheConstant.SYS_DICT_CACHE, allEntries=true)
	public Result<SysDict> delete(@RequestParam(name="id",required=true) String id) {
		Result<SysDict> result = new Result<SysDict>();
		boolean ok = sysDictService.removeById(id);
		if(ok) {
			result.success("删除成功!");
		}else{
			result.error500("删除失败!");
		}
		return result;
	}

	/**
	 * @功能：批量删除
	 * @param ids
	 * @return
	 */
	//@RequiresRoles({"admin"})
	@RequestMapping(value = "/deleteBatch", method = RequestMethod.DELETE)
	@CacheEvict(value= CacheConstant.SYS_DICT_CACHE, allEntries=true)
	public Result<SysDict> deleteBatch(@RequestParam(name="ids",required=true) String ids) {
		Result<SysDict> result = new Result<SysDict>();
		if(oConvertUtils.isEmpty(ids)) {
			result.error500("参数不识别！");
		}else {
			sysDictService.removeByIds(Arrays.asList(ids.split(",")));
			result.success("删除成功!");
		}
		return result;
	}

	/**
	 * @功能：刷新缓存
	 * @return
	 */
	@RequestMapping(value = "/refleshCache")
	public Result<?> refleshCache() {
		Result<?> result = new Result<SysDict>();
		//清空字典缓存
		Set keys = redisTemplate.keys(CacheConstant.SYS_DICT_CACHE + "*");
		Set keys2 = redisTemplate.keys(CacheConstant.SYS_DICT_TABLE_CACHE + "*");
		Set keys3 = redisTemplate.keys(CacheConstant.SYS_DEPARTS_CACHE + "*");
		Set keys4 = redisTemplate.keys(CacheConstant.SYS_DEPART_IDS_CACHE + "*");
		redisTemplate.delete(keys);
		redisTemplate.delete(keys2);
		redisTemplate.delete(keys3);
		redisTemplate.delete(keys4);
		return result;
	}

	/**
	 * 导出excel
	 *
	 * @param request
	 */
	@RequestMapping(value = "/exportXls")
	public ModelAndView exportXls(SysDict sysDict,HttpServletRequest request) {
		// Step.1 组装查询条件
		QueryWrapper<SysDict> queryWrapper = QueryGenerator.initQueryWrapper(sysDict, request.getParameterMap());
		//Step.2 AutoPoi 导出Excel
		ModelAndView mv = new ModelAndView(new JeecgEntityExcelView());
		List<SysDictPage> pageList = new ArrayList<SysDictPage>();

		List<SysDict> sysDictList = sysDictService.list(queryWrapper);
		for (SysDict dictMain : sysDictList) {
			SysDictPage vo = new SysDictPage();
			BeanUtils.copyProperties(dictMain, vo);
			// 查询机票
			List<SysDictItem> sysDictItemList = sysDictItemService.selectItemsByMainId(dictMain.getId());
			vo.setSysDictItemList(sysDictItemList);
			pageList.add(vo);
		}

		// 导出文件名称
		mv.addObject(NormalExcelConstants.FILE_NAME, "数据字典");
		// 注解对象Class
		mv.addObject(NormalExcelConstants.CLASS, SysDictPage.class);
		// 自定义表格参数
		LoginUser user = (LoginUser) SecurityUtils.getSubject().getPrincipal();
		mv.addObject(NormalExcelConstants.PARAMS, new ExportParams("数据字典列表", "导出人:"+user.getRealname(), "数据字典"));
		// 导出数据列表
		mv.addObject(NormalExcelConstants.DATA_LIST, pageList);
		return mv;
	}

	/**
	 * 通过excel导入数据
	 *
	 * @param request
	 * @param
	 * @return
	 */
	@RequestMapping(value = "/importExcel", method = RequestMethod.POST)
	public Result<?> importExcel(HttpServletRequest request, HttpServletResponse response) {
 		MultipartHttpServletRequest multipartRequest = (MultipartHttpServletRequest) request;
		Map<String, MultipartFile> fileMap = multipartRequest.getFileMap();
		for (Map.Entry<String, MultipartFile> entity : fileMap.entrySet()) {
			MultipartFile file = entity.getValue();// 获取上传文件对象
			ImportParams params = new ImportParams();
			params.setTitleRows(2);
			params.setHeadRows(2);
			params.setNeedSave(true);
			try {
				List<SysDictPage> list = ExcelImportUtil.importExcel(file.getInputStream(), SysDictPage.class, params);
				// 错误信息
				List<String> errorMessage = new ArrayList<>();
				int successLines = 0, errorLines = 0;
				for (int i=0;i< list.size();i++) {
					SysDict po = new SysDict();
					BeanUtils.copyProperties(list.get(i), po);
					po.setDelFlag(CommonConstant.DEL_FLAG_0);
					try {
						Integer integer = sysDictService.saveMain(po, list.get(i).getSysDictItemList());
						if(integer>0){
							successLines++;
						}else{
							errorLines++;
							int lineNumber = i + 1;
							errorMessage.add("第 " + lineNumber + " 行：字典编码已经存在，忽略导入。");
						}
					}  catch (Exception e) {
						errorLines++;
						int lineNumber = i + 1;
						errorMessage.add("第 " + lineNumber + " 行：字典编码已经存在，忽略导入。");
					}
				}
				return ImportExcelUtil.imporReturnRes(errorLines,successLines,errorMessage);
			} catch (Exception e) {
				log.error(e.getMessage(),e);
				return Result.error("文件导入失败:"+e.getMessage());
			} finally {
				try {
					file.getInputStream().close();
				} catch (Exception e) {
					e.printStackTrace();
				}
			}
		}
		return Result.error("文件导入失败！");
	}
	

	/**
	 * 查询被删除的列表
	 * @return
	 */
	@RequestMapping(value = "/deleteList", method = RequestMethod.GET)
	public Result<List<SysDict>> deleteList() {
		Result<List<SysDict>> result = new Result<List<SysDict>>();
		List<SysDict> list = this.sysDictService.queryDeleteList();
		result.setSuccess(true);
		result.setResult(list);
		return result;
	}

	/**
	 * 物理删除
	 * @param id
	 * @return
	 */
	@RequestMapping(value = "/deletePhysic/{id}", method = RequestMethod.DELETE)
	public Result<?> deletePhysic(@PathVariable String id) {
		try {
			sysDictService.deleteOneDictPhysically(id);
			return Result.ok("删除成功!");
		} catch (Exception e) {
			e.printStackTrace();
			return Result.error("删除失败!");
		}
	}

	/**
	 * 取回
	 * @param id
	 * @return
	 */
	@RequestMapping(value = "/back/{id}", method = RequestMethod.PUT)
	public Result<?> back(@PathVariable String id) {
		try {
			sysDictService.updateDictDelFlag(0,id);
			return Result.ok("操作成功!");
		} catch (Exception e) {
			e.printStackTrace();
			return Result.error("操作失败!");
		}
	}

}
