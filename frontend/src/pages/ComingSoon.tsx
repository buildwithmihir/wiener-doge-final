import { Link } from 'react-router-dom'
import { EmptyState, PageTitle } from '../components/ui'

export default function ComingSoon({ title }: { title: string }) {
  return (
    <>
      <PageTitle title={title} />
      <EmptyState
        title="Coming next"
        text="This screen is built in the next steps of the project."
        action={
          <Link to="/" className="btn-primary">
            Back to markets
          </Link>
        }
      />
    </>
  )
}
