package org.jeecg.modules.system.aspect;

import java.lang.reflect.Method;
import java.util.Date;

import javax.servlet.http.HttpServletRequest;

import org.apache.shiro.SecurityUtils;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Pointcut;
import org.aspectj.lang.reflect.MethodSignature;
import org.jeecg.common.aspect.annotation.AutoLog;
import org.jeecg.common.constant.CommonConstant;
import org.jeecg.common.system.vo.LoginUser;
import org.jeecg.common.util.SpringContextUtils;
import org.jeecg.modules.system.entity.SysLog;
import org.jeecg.modules.system.service.AutoLogWriter;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;


/**
 * 系统日志，切面处理类
 * 
 * @Author scott
 * @email jeecgos@163.com
 * @Date 2018年1月14日
 */
@Aspect
@Component
public class AutoLogAspect {
	private static final Logger LOG = LoggerFactory.getLogger(AutoLogAspect.class);
	@Autowired
	private AutoLogWriter auditWriter;
	
	@Pointcut("@annotation(org.jeecg.common.aspect.annotation.AutoLog)")
	public void logPointCut() { 
		
	}

	@Around("logPointCut()")
	public Object around(ProceedingJoinPoint point) throws Throwable {
		long beginTime = System.currentTimeMillis();
		//执行方法
		Object result = point.proceed();
		//执行时长(毫秒)
		long time = System.currentTimeMillis() - beginTime;

		// Non-critical audit must not turn an already completed business write into
		// a failed response. Never retry the business method or log request/SQL data.
		String operation = "unavailable";
		try {
			MethodSignature signature = (MethodSignature) point.getSignature();
			operation = signature.getDeclaringTypeName() + "." + signature.getName() + "()";
			saveSysLog(signature, operation, time);
		} catch (Exception auditFailure) {
			LOG.warn("audit_write_failed method={} failureType={}", operation, auditFailure.getClass().getName());
		}

		return result;
	}

	private void saveSysLog(MethodSignature signature, String operation, long time) {
		Method method = signature.getMethod();

		SysLog sysLog = new SysLog();
		AutoLog syslog = method.getAnnotation(AutoLog.class);
		if(syslog != null){
			//注解上的描述,操作日志内容
			sysLog.setLogContent(syslog.value());
			sysLog.setLogType(syslog.logType());
			
		}

		//请求的方法名
		String methodName = signature.getName();
		sysLog.setMethod(operation);
		
		
		//设置操作类型
		if (Integer.valueOf(CommonConstant.LOG_TYPE_2).equals(sysLog.getLogType())) {
			sysLog.setOperateType(getOperateType(methodName, syslog.operateType()));
		}

		//获取request
		HttpServletRequest request = SpringContextUtils.getHttpServletRequest();
		// Metadata only: never persist arguments, query strings, bodies, tokens or
		// forwarded headers. Domain-specific histories have their own access policy.
		sysLog.setRequestParam(null);
		sysLog.setRequestType(request.getMethod());
		sysLog.setIp(request.getRemoteAddr());

		//获取登录用户信息
		LoginUser sysUser = (LoginUser)SecurityUtils.getSubject().getPrincipal();
		if(sysUser!=null){
			sysLog.setUserid(sysUser.getUsername());
			sysLog.setUsername(sysUser.getRealname());

		}
		//耗时
		sysLog.setCostTime(time);
		sysLog.setCreateTime(new Date());
		//保存系统日志
		auditWriter.save(sysLog);
	}
	/**
	 * 获取操作类型
	 */
	private int getOperateType(String methodName,int operateType) {
		if (operateType > 0) {
			return operateType;
		}
        if (methodName.startsWith("list")) {
        	return CommonConstant.OPERATE_TYPE_1;
		}
        if (methodName.startsWith("add")) {
        	return CommonConstant.OPERATE_TYPE_2;
		}
        if (methodName.startsWith("edit")) {
        	return CommonConstant.OPERATE_TYPE_3;
		}
        if (methodName.startsWith("delete")) {
        	return CommonConstant.OPERATE_TYPE_4;
		}
        if (methodName.startsWith("import")) {
        	return CommonConstant.OPERATE_TYPE_5;
		}
        if (methodName.startsWith("export")) {
        	return CommonConstant.OPERATE_TYPE_6;
		}
		return CommonConstant.OPERATE_TYPE_1;
	}
}
