package org.jeecg.modules.teaching.service.impl;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import org.jeecg.modules.system.entity.SysDepart;
import org.jeecg.modules.system.entity.SysUser;
import org.jeecg.modules.system.mapper.SysDepartMapper;
import org.jeecg.modules.system.mapper.SysUserMapper;
import org.jeecg.modules.teaching.service.TeachingWorkAttachmentService;
import org.jeecg.modules.teaching.service.TeachingAccessService;
import org.jeecg.common.exception.JeecgBootException;
import org.jeecg.modules.teaching.entity.TeachingWork;
import org.jeecg.modules.teaching.entity.TeachingWorkCorrect;
import org.jeecg.modules.teaching.entity.TeachingWorkComment;
import org.jeecg.modules.teaching.entity.TeachingCourse;
import org.jeecg.modules.teaching.entity.TeachingCourseUnit;
import org.jeecg.modules.teaching.entity.TeachingCourseDept;
import org.jeecg.modules.teaching.entity.TeachingAdditionalWork;
import org.jeecg.modules.teaching.mapper.TeachingCourseMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseUnitMapper;
import org.jeecg.modules.teaching.mapper.TeachingCourseDeptMapper;
import org.jeecg.modules.teaching.mapper.TeachingAdditionalWorkMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkCorrectMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkCommentMapper;
import org.jeecg.modules.teaching.mapper.TeachingWorkMapper;
import org.jeecg.modules.teaching.model.AdditionalWorkModel;
import org.jeecg.modules.teaching.model.StudentWorkModel;
import org.jeecg.modules.teaching.service.ITeachingWorkService;
import org.jeecg.modules.teaching.vo.StudentWorkSendVO;
import org.springframework.stereotype.Service;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationAdapter;
import org.springframework.transaction.support.TransactionSynchronizationManager;
import org.springframework.util.StringUtils;

import java.io.Serializable;
import java.util.*;
import java.util.stream.Collectors;

/**
 * @Description: 作业列表
 * @Author: jeecg-boot
 * @Date:   2020-04-12
 * @Version: V1.0
 */
@Service
public class TeachingWorkServiceImpl extends ServiceImpl<TeachingWorkMapper, TeachingWork> implements ITeachingWorkService {
	@Autowired
	SysUserMapper sysUserMapper;
	@Autowired
	private SysDepartMapper sysDepartMapper;
	@Autowired
	private TeachingWorkMapper teachingWorkMapper;
	@Autowired
	private TeachingWorkCorrectMapper teachingWorkCorrectMapper;
	@Autowired
	private TeachingWorkCommentMapper teachingWorkCommentMapper;
	@Autowired
	private TeachingWorkAttachmentService workAttachmentService;
	@Autowired
	private TeachingAccessService teachingAccessService;
	@Autowired
	private TeachingCourseMapper teachingCourseMapper;
	@Autowired
	private TeachingCourseUnitMapper teachingCourseUnitMapper;
	@Autowired
	private TeachingCourseDeptMapper teachingCourseDeptMapper;
	@Autowired
	private TeachingAdditionalWorkMapper teachingAdditionalWorkMapper;


	@Override
	@Transactional
	public void saveMain(TeachingWork teachingWork, List<TeachingWorkCorrect> teachingWorkCorrectList,List<TeachingWorkComment> teachingWorkCommentList) {
		teachingWorkMapper.insert(teachingWork);
		if(teachingWorkCorrectList!=null && teachingWorkCorrectList.size()>0) {
			for(TeachingWorkCorrect entity:teachingWorkCorrectList) {
				//外键设置
				entity.setWorkId(teachingWork.getId());
				teachingWorkCorrectMapper.insert(entity);
			}
		}
		if(teachingWorkCommentList!=null && teachingWorkCommentList.size()>0) {
			for(TeachingWorkComment entity:teachingWorkCommentList) {
				//外键设置
				entity.setWorkId(teachingWork.getId());
				teachingWorkCommentMapper.insert(entity);
			}
		}
	}

	@Override
	@Transactional
	public void updateMain(TeachingWork teachingWork,List<TeachingWorkCorrect> teachingWorkCorrectList,List<TeachingWorkComment> teachingWorkCommentList) {
		teachingWorkMapper.updateById(teachingWork);
		
		// A partial edit must not clear a collection that the caller did not send.
		// Null (including an omitted property) preserves it; [] explicitly clears it.
		// Keep replacement inside this transaction so a failed insert restores all rows.
		if(teachingWorkCorrectList!=null) {
			teachingWorkCorrectMapper.deleteByMainId(teachingWork.getId());
			for(TeachingWorkCorrect entity:teachingWorkCorrectList) {
				//外键设置
				entity.setWorkId(teachingWork.getId());
				teachingWorkCorrectMapper.insert(entity);
			}
		}
		if(teachingWorkCommentList!=null) {
			teachingWorkCommentMapper.deleteByMainId(teachingWork.getId());
			for(TeachingWorkComment entity:teachingWorkCommentList) {
				//外键设置
				entity.setWorkId(teachingWork.getId());
				teachingWorkCommentMapper.insert(entity);
			}
		}
	}

	@Override
	@Transactional
	public void delMain(String id) {
		TeachingWork work = this.getById(id);
		if (work == null){
			return;
		}
		teachingWorkCorrectMapper.deleteByMainId(id);
		teachingWorkCommentMapper.deleteByMainId(id);
		teachingWorkMapper.deleteById(id);
		// Sent copies share these IDs. Never remove bytes before the whole delete
		// transaction (including a batch and its feedback rows) has committed.
		TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronizationAdapter() {
			@Override
			public void afterCommit() {
				workAttachmentService.cleanupAfterWorkDeletion(work.getWorkCover());
				if (!Objects.equals(work.getWorkCover(), work.getWorkFile())) {
					workAttachmentService.cleanupAfterWorkDeletion(work.getWorkFile());
				}
			}
		});
	}

	@Override
	@Transactional
	public void delBatchMain(Collection<? extends Serializable> idList) {
		for(Serializable id:idList) {
			this.delMain((String) id);
		}
	}

	@Override
	public StudentWorkModel studentWorkInfo(String workId) {
		return this.baseMapper.studentWorkInfo(workId);
	}

	@Override
	public boolean incrementViewCount(String workId) {
		return this.baseMapper.incrementViewCount(workId) == 1;
	}

	@Override
	public boolean incrementStarCount(String workId) {
		return this.baseMapper.incrementStarCount(workId) == 1;
	}

	@Override
	public Page<StudentWorkModel> listWorkModel(Page<StudentWorkModel> page, QueryWrapper<StudentWorkModel> queryWrapper,List<String> deptIds) {
		return page.setRecords(this.baseMapper.listWorkModel(page, queryWrapper,deptIds));
	}

	@Override
	@Transactional(rollbackFor = Exception.class)
	public int sendWork(StudentWorkSendVO studentWorkSendVO) {
		if (studentWorkSendVO == null || !StringUtils.hasText(studentWorkSendVO.getSendWorkId())
				|| studentWorkSendVO.getUserIdList() == null || studentWorkSendVO.getUserIdList().isEmpty()) {
			throw new JeecgBootException("请选择源作品和接收用户");
		}
		List<String> recipientIds = new ArrayList<>(studentWorkSendVO.getUserIdList());
		if (recipientIds.stream().anyMatch(id -> !StringUtils.hasText(id))
				|| new HashSet<>(recipientIds).size() != recipientIds.size()) {
			throw new JeecgBootException("接收用户不能为空或重复");
		}
		Collections.sort(recipientIds);
		TeachingWork sourceWork = teachingWorkMapper.selectOne(new QueryWrapper<TeachingWork>()
				.eq("id", studentWorkSendVO.getSendWorkId()).last("FOR UPDATE"));
		teachingAccessService.requireReadWork(sourceWork);
		if (sourceWork == null || !Integer.valueOf(0).equals(sourceWork.getDelFlag())) {
			throw new JeecgBootException("源作品不存在或已删除");
		}
		if (StringUtils.hasText(sourceWork.getCourseId()) && StringUtils.hasText(sourceWork.getAdditionalId())) {
			throw new JeecgBootException("源作品任务归属异常，不能克隆");
		}
		// Validate the entire batch before INSERT. Fixed user-lock order serializes
		// concurrent clone batches for the same recipients without using names as IDs.
		Map<String, String> recipientDeparts = new HashMap<>();
		for (String userId : recipientIds) {
			SysUser user = sysUserMapper.selectOne(new QueryWrapper<SysUser>().eq("id", userId).last("FOR UPDATE"));
			if (user == null || !userId.equals(user.getId()) || !Integer.valueOf(0).equals(user.getDelFlag()) || !Integer.valueOf(1).equals(user.getStatus())) {
				throw new JeecgBootException("接收用户不存在或不可用，本批次未创建作品");
			}
			TeachingWork recipient = new TeachingWork();
			recipient.setUserId(userId);
			recipient.setDepartId(cloneTaskDepart(sourceWork, userId));
			teachingAccessService.requireManageWork(recipient);
			recipientDeparts.put(userId, recipient.getDepartId());
			if (StringUtils.hasText(sourceWork.getCourseId()) || StringUtils.hasText(sourceWork.getAdditionalId())) {
				QueryWrapper<TeachingWork> conflict = new QueryWrapper<TeachingWork>().eq("user_id", userId).eq("del_flag", 0);
				if (StringUtils.hasText(sourceWork.getCourseId())) conflict.eq("course_id", sourceWork.getCourseId());
				else conflict.eq("additional_id", sourceWork.getAdditionalId());
				if (!teachingWorkMapper.selectList(conflict.last("FOR UPDATE")).isEmpty()) {
					throw new JeecgBootException("接收用户已有该任务的作品，请继续编辑原作品；本批次未创建作品");
				}
			}
		}
		for (String userId : recipientIds) {
			// Copy only content and task identity. A clone has its own draft status,
			// metrics, audit identity and cloud namespace, with no feedback children.
			TeachingWork work = new TeachingWork();
			work.setUserId(userId);
			work.setDepartId(recipientDeparts.get(userId));
			work.setCourseId(sourceWork.getCourseId());
			work.setAdditionalId(sourceWork.getAdditionalId());
			work.setWorkName(sourceWork.getWorkName());
			work.setWorkType(sourceWork.getWorkType());
			work.setWorkFile(sourceWork.getWorkFile());
			work.setWorkCover(sourceWork.getWorkCover());
			work.setWorkScene(StringUtils.hasText(work.getCourseId()) ? "course"
					: StringUtils.hasText(work.getAdditionalId()) ? "additional" : "create");
			work.setHasCloudData(false);
			work.setWorkStatus("0");
			work.setViewNum(0);
			work.setStarNum(0);
			work.setCollectNum(0);
			work.setDelFlag(0);
			if (teachingWorkMapper.insert(work) != 1) throw new JeecgBootException("作品克隆失败，请稍后重试");
		}
		return recipientIds.size();
	}

	/** Validate the recipient, independent of the actor's administrative role.
	 * A task-bound source keeps its class; an unbound source derives a valid class
	 * as submission does. Standalone works have no task eligibility restriction. */
	private String cloneTaskDepart(TeachingWork source, String userId) {
		if (!StringUtils.hasText(source.getCourseId()) && !StringUtils.hasText(source.getAdditionalId())) {
			return source.getDepartId();
		}
		List<SysDepart> departments = sysDepartMapper.queryUserDeparts(userId);
		Set<String> memberships = departments == null ? Collections.emptySet() : departments.stream()
				.filter(depart -> !"1".equals(depart.getDelFlag())).map(SysDepart::getId).collect(Collectors.toSet());
		List<String> eligible;
		boolean sharedCourse = false;
		if (StringUtils.hasText(source.getCourseId())) {
			TeachingCourseUnit unit = teachingCourseUnitMapper.selectOne(new QueryWrapper<TeachingCourseUnit>()
					.eq("id", source.getCourseId()).last("FOR UPDATE"));
			TeachingCourse course = unit == null ? null : teachingCourseMapper.selectOne(new QueryWrapper<TeachingCourse>()
					.eq("id", unit.getCourseId()).last("FOR UPDATE"));
			if (unit == null || course == null || Integer.valueOf(1).equals(unit.getDelFlag())
					|| Integer.valueOf(1).equals(course.getDelFlag())) {
				throw new JeecgBootException("源作品任务不存在或已删除，本批次未创建作品");
			}
			sharedCourse = Boolean.TRUE.equals(course.getIsShared());
			eligible = memberships.isEmpty() ? Collections.emptyList() : teachingCourseDeptMapper.selectList(
					new QueryWrapper<TeachingCourseDept>().eq("course_id", course.getId()).in("dept_id", memberships).last("FOR UPDATE"))
					.stream().map(TeachingCourseDept::getDeptId).filter(memberships::contains).distinct().sorted().collect(Collectors.toList());
		} else {
			TeachingAdditionalWork task = teachingAdditionalWorkMapper.selectOne(new QueryWrapper<TeachingAdditionalWork>()
					.eq("id", source.getAdditionalId()).last("FOR UPDATE"));
			if (task == null || !Integer.valueOf(1).equals(task.getStatus()) || !StringUtils.hasText(task.getWorkDept())) {
				throw new JeecgBootException("源作品任务不存在或已停用，本批次未创建作品");
			}
			eligible = Arrays.stream(task.getWorkDept().split(",")).map(String::trim).filter(memberships::contains)
					.distinct().sorted().collect(Collectors.toList());
		}
		if (StringUtils.hasText(source.getDepartId())) {
			if (eligible.contains(source.getDepartId())) return source.getDepartId();
		} else {
			if (!eligible.isEmpty()) return eligible.get(0);
			if (sharedCourse) return "";
		}
		throw new JeecgBootException("接收用户不属于源作品班级或已无任务提交资格，本批次未创建作品");
	}

	@Override
	public List<AdditionalWorkModel> userAdditionalWork(String userId, String departId, Boolean submit, Integer status) {
		List<SysDepart> memberships = sysDepartMapper.queryUserClassroom(userId);
		if (memberships == null) return Collections.emptyList();
		List<SysDepart> classrooms = memberships.stream()
				.filter(depart -> !"1".equals(depart.getDelFlag()))
				.filter(depart -> !StringUtils.hasText(departId) || depart.getId().equals(departId.trim()))
				.sorted(Comparator.comparing(SysDepart::getId)).collect(Collectors.toList());
		if (classrooms.isEmpty()) return Collections.emptyList();
		List<String> departIds = classrooms.stream().map(SysDepart::getId).collect(Collectors.toList());
		List<AdditionalWorkModel> rows = this.baseMapper.userAdditionalWork(userId, departIds, submit, status);
		List<AdditionalWorkModel> result = new ArrayList<>();
		for (AdditionalWorkModel row : rows) {
			Set<String> assigned = Arrays.stream(row.getWorkDept().split(","))
					.map(String::trim).collect(Collectors.toSet());
			// Keep the saved work's class, as the submission service does. An
			// assignment shared with another class must not rebind that work.
			Optional<SysDepart> classroom = classrooms.stream().filter(depart -> assigned.contains(depart.getId()))
					.filter(depart -> !StringUtils.hasText(row.getMineWorkDepartId()) || depart.getId().equals(row.getMineWorkDepartId()))
					.findFirst();
			if (classroom.isPresent()) {
				row.setDepartId(classroom.get().getId());
				row.setDepartName(classroom.get().getDepartName());
				result.add(row);
			}
		}
		return result;
	}

}
