const onlineRoutes = {
    'modules/online/cgform/OnlCgformHeadList': 'OnlCgformHeadList',
    'modules/online/cgform/OnlCgformCopyList': 'OnlCgformCopyList',
    'modules/online/cgform/auto/OnlCgformAutoList': 'OnlCgformAutoList',
    'modules/online/cgform/auto/OnlCgformTreeList': 'OnlCgformTreeList',
    'modules/online/cgform/auto/erp/OnlCgformErpList': 'OnlCgformErpList',
    'modules/online/cgform/auto/innerTable/OnlCgformInnerTableList': 'OnlCgformInnerTableList',
    'modules/online/cgreport/OnlCgreportHeadList': 'OnlCgreportHeadList',
    'modules/online/cgreport/auto/OnlCgreportAutoList': 'OnlCgreportAutoList'
}

export function resolveOnlineRoute (path) {
    if (!Object.prototype.hasOwnProperty.call(onlineRoutes, path)) return null
    const name = onlineRoutes[path]
    return () => import(/* webpackChunkName: "online-forms" */ './onlineComponents')
        .then(module => module.default[name])
}
