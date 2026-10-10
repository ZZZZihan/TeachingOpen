package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.LambdaQueryWrapper;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import lombok.extern.slf4j.Slf4j;
import org.apache.shiro.SecurityUtils;
import org.apache.shiro.authz.UnauthorizedException;
import org.jeecg.common.api.vo.Result;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.RedisUtil;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.model.DepartIdModel;
import org.jeecg.modules.system.service.ISysDepartService;
import org.jeecg.modules.system.service.ISysUserService;
import org.jeecg.modules.system.service.ISysUserDepartService;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.jeecg.modules.teaching.mapper.TeachingAdditionalWorkMapper;
import org.jeecg.modules.teaching.model.MineAdditionalWorkModel;
import org.jeecg.modules.teaching.service.ITeachingAdditionalWorkService;
import org.jeecg.modules.teaching.service.ITeachingDepartDayLogService;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import java.util.*;
import java.util.stream.Collectors;

/**
 * @Description: 附加作业
 */
@Slf4j
@Service
public class TeachingAdditionalWorkServiceImpl extends ServiceImpl<TeachingAdditionalWorkMapper, TeachingAdditionalWork> implements ITeachingAdditionalWorkService {

    @Autowired
    private ISysUserDepartService sysUserDepartService;

    @Autowired
    private ISysUserService sysUserService;
    @Autowired
    private ISysDepartService sysDepartService;
    @Autowired
    private ITeachingDepartDayLogService teachingDepartDayLogService;
    @Autowired
    private RedisUtil redisUtil;

    @Override
    public Result<MineAdditionalWorkModel> getWorkInfo(String id) {
        Result<MineAdditionalWorkModel> result = new Result();
        result.setResult(this.baseMapper.getWorkInfo(id));
        return result;
    }

    @Override
    public Result<List<MineAdditionalWorkModel>> mineAdditionalWork(String userId) {
        Result<List<MineAdditionalWorkModel>> result = new Result();
        //查询学生所有班级
        List<DepartIdModel> depts = sysUserDepartService.queryDepartIdsOfUser(userId);
        List<MineAdditionalWorkModel> all = new ArrayList<>();
        for(DepartIdModel departIdModel: depts){
            List<MineAdditionalWorkModel> list = this.baseMapper.getByDeptId(departIdModel.getKey(), userId);
            all.addAll(list);
        }
        result.setResult(all);
        return result;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Result<?> addNewAdditionalWork(TeachingAdditionalWork teachingAdditionalWork) {
        Writer writer = requireWriter();
        TeachingAdditionalWork work = editableFields(teachingAdditionalWork);
        Set<String> departments = requireDepartments(work.getWorkDept());
        requireManagedDepartments(writer, departments);
        work.setWorkDept(String.join(",", departments));
        work.setCreateBy(writer.user.getUsername());
        work.setCreateTime(new Date());
        work.setSysOrgCode(writer.user.getOrgCode());
        if (baseMapper.insert(work) != 1 || work.getId() == null) {
            throw new JeecgBootException("附加作业保存失败");
        }
        recordAssignments(work.getId(), departments);
        return Result.ok("添加成功！");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Result<?> editAdditionalWork(TeachingAdditionalWork request) {
        Writer writer = requireWriter();
        if (request == null) throw new JeecgBootException("附加作业不能为空");
        List<TeachingAdditionalWork> existing = lockWorks(Collections.singletonList(request.getId()));
        TeachingAdditionalWork previous = existing.get(0);
        requireOwnership(writer, previous);
        TeachingAdditionalWork work = editableFields(request);
        Set<String> departments = requireDepartments(work.getWorkDept());
        requireManagedDepartments(writer, departments);
        work.setId(previous.getId());
        work.setWorkDept(String.join(",", departments));
        work.setUpdateBy(writer.user.getUsername());
        work.setUpdateTime(new Date());
        if (baseMapper.updateById(work) != 1) throw new JeecgBootException("附加作业更新失败");
        departments.removeAll(splitIds(previous.getWorkDept(), "原作业班级"));
        recordAssignments(work.getId(), departments);
        return Result.ok("编辑成功!");
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Result<?> deleteAdditionalWorks(List<String> requested) {
        Writer writer = requireWriter();
        List<TeachingAdditionalWork> works = lockWorks(requested);
        // Validate every object before deleting any of them.
        works.forEach(work -> requireOwnership(writer, work));
        List<String> ids = works.stream().map(TeachingAdditionalWork::getId).collect(Collectors.toList());
        if (baseMapper.deleteBatchIds(ids) != ids.size()) throw new JeecgBootException("附加作业删除失败");
        return Result.ok("删除成功!");
    }

    private Writer requireWriter() {
        Object principal = SecurityUtils.getSubject().getPrincipal();
        if (!(principal instanceof LoginUser)) throw new UnauthorizedException("没有附加作业管理权限");
        String id = ((LoginUser) principal).getId();
        SysUser current = sysUserService.getOne(new LambdaQueryWrapper<SysUser>()
                .eq(SysUser::getId, id).last("FOR UPDATE"));
        if (current == null || !Objects.equals(id, current.getId())
                || !Integer.valueOf(1).equals(current.getStatus())) {
            throw new UnauthorizedException("账户不可用");
        }
        // The authenticated principal can have an older role or department cache.
        List<String> roles = sysUserService.getRoleById(id);
        boolean administrator = roles != null && (roles.contains("admin") || roles.contains("dev"));
        if (!administrator && (roles == null || !roles.contains("teacher"))) {
            throw new UnauthorizedException("没有附加作业管理权限");
        }
        Set<String> managed = new HashSet<>();
        if (!administrator && current.getDepartIds() != null && !current.getDepartIds().trim().isEmpty()) {
            List<String> descendants = sysDepartService.getMySubDepIdsByDepId(current.getDepartIds());
            if (descendants != null) managed.addAll(descendants);
        }
        return new Writer(current, administrator, managed);
    }

    private List<TeachingAdditionalWork> lockWorks(List<String> requested) {
        Set<String> ids = normalizedIds(requested, "附加作业");
        List<TeachingAdditionalWork> works = baseMapper.selectList(new LambdaQueryWrapper<TeachingAdditionalWork>()
                .in(TeachingAdditionalWork::getId, ids).orderByAsc(TeachingAdditionalWork::getId).last("FOR UPDATE"));
        Set<String> actual = works.stream().map(TeachingAdditionalWork::getId).collect(Collectors.toSet());
        if (!actual.equals(ids)) throw new JeecgBootException("未找到全部附加作业");
        return works;
    }

    private void requireOwnership(Writer writer, TeachingAdditionalWork work) {
        if (writer.administrator) return;
        if (!writer.user.getUsername().equals(work.getCreateBy())) {
            throw new UnauthorizedException("只能管理本人创建的附加作业");
        }
        requireManagedDepartments(writer, splitIds(work.getWorkDept(), "原作业班级"));
    }

    private Set<String> requireDepartments(String requested) {
        Set<String> ids = splitIds(requested, "班级");
        List<SysDepart> departments = sysDepartService.list(new LambdaQueryWrapper<SysDepart>()
                .in(SysDepart::getId, ids).eq(SysDepart::getDelFlag, "0")
                .orderByAsc(SysDepart::getId).last("FOR UPDATE"));
        Set<String> actual = departments.stream().map(SysDepart::getId).collect(Collectors.toSet());
        if (!actual.equals(ids)) throw new JeecgBootException("未找到全部目标班级");
        return ids;
    }

    private void requireManagedDepartments(Writer writer, Set<String> departments) {
        if (!writer.administrator && !writer.managed.containsAll(departments)) {
            throw new UnauthorizedException("只能操作本人管理班级的附加作业");
        }
    }

    private Set<String> splitIds(String requested, String label) {
        return normalizedIds(requested == null ? null : Arrays.asList(requested.split(",")), label);
    }

    private Set<String> normalizedIds(Collection<String> requested, String label) {
        if (requested == null || requested.isEmpty() || requested.size() > 100) {
            throw new JeecgBootException("请选择1至100个" + label);
        }
        Set<String> ids = new TreeSet<>();
        for (String id : requested) {
            if (id == null || id.trim().isEmpty()) throw new JeecgBootException(label + "ID不能为空");
            ids.add(id.trim());
        }
        return ids;
    }

    private TeachingAdditionalWork editableFields(TeachingAdditionalWork request) {
        if (request == null || request.getWorkName() == null || request.getWorkName().trim().isEmpty()) {
            throw new JeecgBootException("请输入附加作业名称");
        }
        if (!Integer.valueOf(0).equals(request.getStatus()) && !Integer.valueOf(1).equals(request.getStatus())) {
            throw new JeecgBootException("附加作业状态只能为未发布或已发布");
        }
        // Legacy forms post the whole previous entity. Copy only editable fields.
        return new TeachingAdditionalWork().setWorkName(request.getWorkName().trim())
                .setCodeType(request.getCodeType()).setWorkDesc(request.getWorkDesc())
                .setWorkCover(request.getWorkCover()).setWorkDocumentUrl(request.getWorkDocumentUrl())
                .setWorkUrl(request.getWorkUrl()).setWorkDept(request.getWorkDept()).setStatus(request.getStatus());
    }

    private void recordAssignments(String workId, Set<String> departments) {
        List<String> keys = new ArrayList<>();
        for (String department : departments) {
            String key = "departLog:addiWorkAssign:" + department;
            if (!redisUtil.sHasKey(key, workId)) {
                // The database log participates in the task transaction.
                teachingDepartDayLogService.recordAdditionalWorkAssignment(department);
                keys.add(key);
            }
        }
        if (!keys.isEmpty()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
                @Override public void afterCommit() {
                    keys.forEach(key -> redisUtil.sSet(key, workId));
                }
            });
        }
    }

    private static class Writer {
        final SysUser user;
        final boolean administrator;
        final Set<String> managed;
        Writer(SysUser user, boolean administrator, Set<String> managed) {
            this.user = user; this.administrator = administrator; this.managed = managed;
        }
    }
}
