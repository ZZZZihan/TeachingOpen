import { postAction } from '@/api/manage'

export const registerAccount = payload => postAction('/sys/user/register', payload)
