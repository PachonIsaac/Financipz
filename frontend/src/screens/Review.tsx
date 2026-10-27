import { PageHeader } from '../components/Layout'
import { EmptyState } from '../components/states'

export function ReviewScreen() {
  return (
    <>
      <PageHeader title="Revisión" />
      <EmptyState
        title="Todo al día"
        description="Aquí aparecerán los movimientos pendientes de confirmar cuando las integraciones estén activas."
      />
    </>
  )
}
