package org.jeecg.modules.system.service.impl;

import java.util.List;

import javax.annotation.Resource;

import org.jeecg.modules.system.entity.SysAnnouncementSend;
import org.jeecg.modules.system.mapper.SysAnnouncementSendMapper;
import org.jeecg.modules.system.model.AnnouncementSendModel;
import org.jeecg.modules.system.service.ISysAnnouncementSendService;
import org.springframework.stereotype.Service;

import com.baomidou.mybatisplus.extension.plugins.pagination.Page;
import com.baomidou.mybatisplus.extension.service.impl.ServiceImpl;

/**
 * @Description: 用户通告阅读标记表
 * @Author: jeecg-boot
 * @Date:  2019-02-21
 * @Version: V1.0
 */
@Service
public class SysAnnouncementSendServiceImpl extends ServiceImpl<SysAnnouncementSendMapper, SysAnnouncementSend> implements ISysAnnouncementSendService {

	@Resource
	private SysAnnouncementSendMapper sysAnnouncementSendMapper;
	
	@Resource private org.jeecg.modules.system.service.AnnouncementAccessService announcementAccess;

	@Override
	public List<String> queryByUserId(String userId) {
		if (!announcementAccess.currentUser().getId().equals(userId)) throw new org.apache.shiro.authz.UnauthorizedException("只能读取本人的通知");
        return sysAnnouncementSendMapper.queryByUserId(userId);
	}

	@Override
	public Page<AnnouncementSendModel> getMyAnnouncementSendPage(Page<AnnouncementSendModel> page,
			AnnouncementSendModel announcementSendModel) {
		 announcementSendModel.setUserId(announcementAccess.currentUser().getId());
         List<AnnouncementSendModel> rows = sysAnnouncementSendMapper.getMyAnnouncementSendList(page, announcementSendModel);
         rows.forEach(org.jeecg.modules.system.service.AnnouncementAccessService::safe);
         return page.setRecords(rows);
	}

}
