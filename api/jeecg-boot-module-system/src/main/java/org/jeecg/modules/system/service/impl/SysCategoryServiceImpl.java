package org.jeecg.modules.system.service.impl;

import java.util.List;
import java.util.Map;

import com.alibaba.fastjson.JSONObject;
import org.jeecg.common.constant.FillRuleConstant;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.util.FillRuleUtil;
import org.jeecg.common.util.YouBianCodeUtil;
import org.jeecg.common.util.oConvertUtils;
import org.jeecg.modules.system.entity.SysCategory;
import org.jeecg.modules.system.mapper.SysCategoryMapper;
import org.jeecg.modules.system.model.TreeSelectModel;
import org.jeecg.modules.system.service.ISysCategoryService;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import org.jeecg.modules.system.service.GlobalResourceService;
import org.jeecg.modules.system.entity.SysUser;
import java.util.*;
import org.springframework.transaction.annotation.Transactional;

/**
 * @Description: 分类字典
 * @Author: jeecg-boot
 * @Date:   2019-05-29
 * @Version: V1.0
 */
@Service
public class SysCategoryServiceImpl extends GlobalResourceService<SysCategoryMapper, SysCategory> implements ISysCategoryService {

    @Override protected String entityId(SysCategory value) { return value.getId(); }
    @Override protected SysCategory writable(SysCategory input, boolean editing, SysUser actor) {
        if (input == null) throw invalid();
        SysCategory value = new SysCategory();
        value.setId(editing ? checkedId(input.getId()) : UUID.randomUUID().toString().replace("-", ""));
        value.setName(text(input.getName(), 100, true)); value.setValue(text(input.getValue(), 100, false));
        value.setComment(text(input.getComment(), 200, false));
        String parent = input.getPid() == null || input.getPid().isEmpty() ? ROOT_PID_VALUE : checkedId(input.getPid());
        Set<String> visited = new HashSet<>(); String cursor = parent;
        while (!ROOT_PID_VALUE.equals(cursor)) {
            if (cursor.equals(value.getId()) || !visited.add(cursor) || visited.size() > 64) throw invalid();
            SysCategory ancestor = baseMapper.selectById(cursor);
            if (ancestor == null) throw invalid();
            cursor = ancestor.getPid() == null || ancestor.getPid().isEmpty() ? ROOT_PID_VALUE : ancestor.getPid();
        }
        value.setPid(parent);
        if (input.getCode() != null && !input.getCode().isEmpty()) {
            if (!input.getCode().matches("[A-Za-z0-9]{1,100}")) throw invalid();
            value.setCode(input.getCode());
        }
        if (editing) { value.setUpdateBy(actor.getUsername()); value.setUpdateTime(new Date()); }
        else { value.setCreateBy(actor.getUsername()); value.setCreateTime(new Date()); value.setHasChild("0"); }
        return value;
    }

    @Override protected void insertPrepared(SysCategory value) {
        if (value.getCode() == null) {
            JSONObject form = new JSONObject(); form.put("pid", value.getPid());
            value.setCode((String) FillRuleUtil.executeRule(FillRuleConstant.CATEGORY, form));
        }
        super.insertPrepared(value); markParent(value.getPid());
    }
    @Override protected void updatePrepared(SysCategory value) { super.updatePrepared(value); markParent(value.getPid()); }
    private void markParent(String pid) {
        if (!ROOT_PID_VALUE.equals(pid)) {
            SysCategory parent = new SysCategory(); parent.setId(pid); parent.setHasChild("1");
            if (baseMapper.updateById(parent) != 1) throw invalid();
        }
    }
    @Override @Transactional(rollbackFor = Exception.class)
    public void addSysCategory(SysCategory input) { save(input); }
    @Override @Transactional(rollbackFor = Exception.class)
    public void updateSysCategory(SysCategory input) { updateById(input); }

	@Override
	public List<TreeSelectModel> queryListByCode(String pcode) throws JeecgBootException{
		String pid = ROOT_PID_VALUE;
		if(oConvertUtils.isNotEmpty(pcode)) {
			List<SysCategory> list = baseMapper.selectList(new LambdaQueryWrapper<SysCategory>().eq(SysCategory::getCode, pcode));
			if(list==null || list.size() ==0) {
				throw new JeecgBootException("该编码【"+pcode+"】不存在，请核实!");
			}
			if(list.size()>1) {
				throw new JeecgBootException("该编码【"+pcode+"】存在多个，请核实!");
			}
			pid = list.get(0).getId();
		}
		return baseMapper.queryListByPid(pid,null);
	}

	@Override
	public List<TreeSelectModel> queryListByPid(String pid) {
		if(oConvertUtils.isEmpty(pid)) {
			pid = ROOT_PID_VALUE;
		}
		return baseMapper.queryListByPid(pid,null);
	}

	@Override
	public List<TreeSelectModel> queryListByPid(String pid, Map<String, String> condition) {
		if(oConvertUtils.isEmpty(pid)) {
			pid = ROOT_PID_VALUE;
		}
		Map<String, String> allowed = new java.util.LinkedHashMap<>();
        if (condition != null) condition.forEach((field, value) -> allowed.put(
                org.jeecg.common.system.query.QueryGenerator.requireColumn(SysCategory.class, field), value));
        return baseMapper.queryListByPid(pid, allowed);
	}

	@Override
	public String queryIdByCode(String code) {
		return baseMapper.queryIdByCode(code);
	}

}
