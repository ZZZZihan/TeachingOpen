package org.jeecg.modules.system.mapper;

import java.util.List;

import org.apache.ibatis.annotations.Param;
import org.jeecg.modules.system.entity.SysAnnouncementSend;
import org.jeecg.modules.system.model.AnnouncementSendModel;

import com.baomidou.mybatisplus.core.mapper.BaseMapper;
import com.baomidou.mybatisplus.extension.plugins.pagination.Page;

/**
 * @Description: 用户通告阅读标记表
 * @Author: jeecg-boot
 * @Date:  2019-02-21
 * @Version: V1.0
 */
public interface SysAnnouncementSendMapper extends BaseMapper<SysAnnouncementSend> {
	@org.apache.ibatis.annotations.Update("UPDATE sys_announcement_send SET read_flag='1', read_time=CURRENT_TIMESTAMP "
			+ "WHERE user_id=#{userId} AND annt_id IN (SELECT id FROM sys_announcement WHERE send_status='1' AND del_flag='0' "
			+ "AND (msg_type='USER' OR (msg_type='ALL' AND (end_time IS NULL OR end_time >= "
			+ "COALESCE((SELECT create_time FROM sys_user WHERE id=#{userId}), CURRENT_TIMESTAMP)))))")
	int markAllRead(@Param("userId") String userId);

	public List<String> queryByUserId(@Param("userId") String userId);

	/**
	 * @功能：获取我的消息
	 * @param announcementSendModel
	 * @param pageSize 
	 * @param pageNo 
	 * @return
	 */
	public List<AnnouncementSendModel> getMyAnnouncementSendList(Page<AnnouncementSendModel> page,@Param("announcementSendModel") AnnouncementSendModel announcementSendModel);

}
