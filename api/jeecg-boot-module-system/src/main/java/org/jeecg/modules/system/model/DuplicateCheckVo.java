package org.jeecg.modules.system.model;

import java.io.Serializable;
import io.swagger.annotations.ApiModel;
import io.swagger.annotations.ApiModelProperty;
import lombok.Data;

/**
 * @Title: DuplicateCheckVo
 * @Description: 重复校验VO
 * @Author 张代浩
 * @Date 2019-03-25
 * @Version V1.0
 */
@Data
@ApiModel(value="重复校验数据模型",description="重复校验数据模型")
public class DuplicateCheckVo implements Serializable {
	private static final long serialVersionUID = 1L;

	/** Server-owned form purpose; SQL identifiers are never accepted. */
	@ApiModelProperty(value="校验用途",name="purpose",example="user_username")
	private String purpose;
	
	/**
	 * 字段值
	 */
	@ApiModelProperty(value="字段值",name="fieldVal",example="1000")
	private String fieldVal;
	
	/**
	 * 数据ID
	*/
	@ApiModelProperty(value="数据ID",name="dataId",example="2000")
	private String dataId;

}
