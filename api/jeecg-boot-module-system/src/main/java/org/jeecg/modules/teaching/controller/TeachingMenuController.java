package org.jeecg.modules.teaching.controller;

import com.alibaba.fastjson.JSONArray;
import com.alibaba.fastjson.JSONObject;
import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.teaching.entity.TeachingMenu;
import org.jeecg.modules.teaching.model.TeachingMenuTree;
import org.jeecg.modules.teaching.model.TreeModel;
import org.jeecg.modules.teaching.service.ITeachingMenuService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import java.util.*;
import java.util.stream.Collectors;

/** Public navigation is readable by everyone; all configuration uses current admin/dev authorization. */
@RestController
@RequestMapping("/teaching/menu")
public class TeachingMenuController {
    private final ITeachingMenuService teachingMenuService;
    public TeachingMenuController(ITeachingMenuService teachingMenuService) { this.teachingMenuService = teachingMenuService; }

    @GetMapping("/getUserMenu")
    public Result<?> getUserMenu() {
        JSONArray result = new JSONArray();
        getPermissionJsonArray(result, teachingMenuService.listPublic(), null);
        return Result.ok(result);
    }
    private LambdaQueryWrapper<TeachingMenu> visibleQuery() {
        return new LambdaQueryWrapper<TeachingMenu>().eq(TeachingMenu::getDelFlag, CommonConstant.DEL_FLAG_0)
                .orderByAsc(TeachingMenu::getSortNo);
    }
    @GetMapping("/list")
    public Result<?> list() {
        List<TeachingMenuTree> result = new ArrayList<>();
        getTreeList(result, teachingMenuService.listManaged(visibleQuery()), null);
        return Result.ok(result);
    }
    @GetMapping("/getSystemMenuList")
    public Result<?> getSystemMenuList() {
        return Result.ok(teachingMenuService.listManaged(visibleQuery().eq(TeachingMenu::getMenuType, 0))
                .stream().map(TeachingMenuTree::new).collect(Collectors.toList()));
    }
    @GetMapping("/getSystemSubmenu")
    public Result<?> getSystemSubmenu(@RequestParam("parentId") String parentId) {
        return Result.ok(teachingMenuService.listManaged(visibleQuery().eq(TeachingMenu::getParentId, parentId))
                .stream().map(TeachingMenuTree::new).collect(Collectors.toList()));
    }
    @GetMapping("/getSystemSubmenuBatch")
    public Result<?> getSystemSubmenuBatch(@RequestParam("parentIds") String parentIds) {
        List<TeachingMenu> rows = teachingMenuService.listManaged(visibleQuery().in(TeachingMenu::getParentId, Arrays.asList(parentIds.split(","))));
        Map<String, List<TeachingMenuTree>> result = new LinkedHashMap<>();
        for (TeachingMenu row : rows) result.computeIfAbsent(row.getParentId(), key -> new ArrayList<>()).add(new TeachingMenuTree(row));
        return Result.ok(result);
    }
    @PostMapping("/add")
    public Result<?> add(@RequestBody TeachingMenu menu) { teachingMenuService.addPermission(menu); return Result.ok("添加成功！"); }
    @RequestMapping(value = "/edit", method = {RequestMethod.PUT, RequestMethod.POST})
    public Result<?> edit(@RequestBody TeachingMenu menu) { teachingMenuService.editPermission(menu); return Result.ok("修改成功！"); }
    @DeleteMapping("/delete")
    public Result<?> delete(@RequestParam("id") String id) { teachingMenuService.deletePermission(id); return Result.ok("删除成功！"); }
    @DeleteMapping("/deleteBatch")
    public Result<?> deleteBatch(@RequestParam("ids") String ids) {
        teachingMenuService.deletePermissions(Arrays.asList(ids.split(",", -1)));
        return Result.ok("删除成功！");
    }
    @GetMapping("/queryTreeList")
    public Result<?> queryTreeList() {
        List<TeachingMenu> rows = teachingMenuService.listManaged(visibleQuery());
        List<TreeModel> trees = new ArrayList<>(); getTreeModelList(trees, rows, null);
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("treeList", trees); result.put("ids", rows.stream().map(TeachingMenu::getId).collect(Collectors.toList()));
        return Result.ok(result);
    }
    @GetMapping("/queryListAsync")
    public Result<?> queryAsync(@RequestParam(name = "pid", required = false) String parentId) {
        return Result.ok(teachingMenuService.queryListByParentId(parentId));
    }
    @ExceptionHandler(UnauthorizedException.class)
    public ResponseEntity<Result<?>> forbidden(UnauthorizedException ignored) {
        return ResponseEntity.status(403).body(Result.error(403, "仅当前有效的管理员可管理教学菜单"));
    }
    @ExceptionHandler(JeecgBootException.class)
    public ResponseEntity<Result<?>> invalid(JeecgBootException error) {
        return ResponseEntity.badRequest().body(Result.error(400, error.getMessage()));
    }

	private void getTreeList(List<TeachingMenuTree> treeList, List<TeachingMenu> metaList, TeachingMenuTree temp) {
		for (TeachingMenu permission : metaList) {
			String tempPid = permission.getParentId();
			TeachingMenuTree tree = new TeachingMenuTree(permission);
			if (temp == null && oConvertUtils.isEmpty(tempPid)) {
				treeList.add(tree);
				if (!tree.getIsLeaf()) {
					getTreeList(treeList, metaList, tree);
				}
			} else if (temp != null && tempPid != null && tempPid.equals(temp.getId())) {
				temp.getChildren().add(tree);
				if (!tree.getIsLeaf()) {
					getTreeList(treeList, metaList, tree);
				}
			}

		}
	}

	private void getTreeModelList(List<TreeModel> treeList, List<TeachingMenu> metaList, TreeModel temp) {
		for (TeachingMenu permission : metaList) {
			String tempPid = permission.getParentId();
			TreeModel tree = new TreeModel(permission);
			if (temp == null && oConvertUtils.isEmpty(tempPid)) {
				treeList.add(tree);
				if (!tree.getIsLeaf()) {
					getTreeModelList(treeList, metaList, tree);
				}
			} else if (temp != null && tempPid != null && tempPid.equals(temp.getKey())) {
				temp.getChildren().add(tree);
				if (!tree.getIsLeaf()) {
					getTreeModelList(treeList, metaList, tree);
				}
			}

		}
	}


	/**
	  *  获取菜单JSON数组
	 * @param jsonArray
	 * @param metaList
	 * @param parentJson
	 */
	private void getPermissionJsonArray(JSONArray jsonArray, List<TeachingMenu> metaList, JSONObject parentJson) {
		for (TeachingMenu permission : metaList) {
			if (permission.getMenuType() == null) {
				continue;
			}
			String tempPid = permission.getParentId();
			JSONObject json = getPermissionJsonObject(permission);
			if(json==null) {
				continue;
			}
			if (parentJson == null && oConvertUtils.isEmpty(tempPid)) {
				jsonArray.add(json);
				if (!permission.isLeaf()) {
					getPermissionJsonArray(jsonArray, metaList, json);
				}
			} else if (parentJson != null && oConvertUtils.isNotEmpty(tempPid) && tempPid.equals(parentJson.getString("id"))) {
				// 类型( 0：一级菜单 1：子菜单 2：按钮 )
				if (permission.getMenuType().equals(CommonConstant.MENU_TYPE_1) || permission.getMenuType().equals(CommonConstant.MENU_TYPE_0)) {
					if (parentJson.containsKey("children")) {
						parentJson.getJSONArray("children").add(json);
					} else {
						JSONArray children = new JSONArray();
						children.add(json);
						parentJson.put("children", children);
					}
					if (!permission.isLeaf()) {
						getPermissionJsonArray(jsonArray, metaList, json);
					}
				}
			}
		}
	}

	/**
	 * 根据菜单配置生成路由json
	 * @param permission
	 * @return
	 */
		private JSONObject getPermissionJsonObject(TeachingMenu permission) {
		JSONObject json = new JSONObject();
		// 类型(0：一级菜单 1：子菜单 2：按钮)
		if (permission.getMenuType().equals(CommonConstant.MENU_TYPE_0) || permission.getMenuType().equals(CommonConstant.MENU_TYPE_1)) {
			json.put("id", permission.getId());
			json.put("route", permission.isRoute());// 表示生成路由
			json.put("title", permission.getName());
			json.put("url", permission.getUrl());
			json.put("needLogin", permission.getNeedLogin());
			//外链菜单打开方式
			json.put("internalOrExternal", permission.isInternalOrExternal());
			if (oConvertUtils.isNotEmpty(permission.getIcon())) {
				json.put("icon", permission.getIcon());
			}
		}
		return json;
	}
}
