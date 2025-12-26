import Box, { type BoxProps } from '@mui/material/Box'
import { useMemo, useState } from 'react'

type Props = Omit<BoxProps<'img'>, 'component'> & {
  src: string
  alt: string
}

export function Screenshot({ src, alt, sx, onError, ...rest }: Props) {
  const [errored, setErrored] = useState(false)

  const resolvedSrc = useMemo(() => {
    if (errored) return '/assets/placeholder.svg'
    return src
  }, [errored, src])

  return (
    <Box
      component="img"
      src={resolvedSrc}
      alt={alt}
      loading="lazy"
      onError={(e) => {
        setErrored(true)
        onError?.(e)
      }}
      sx={[
        {
          width: '100%',
          borderRadius: 2,
          border: '1px solid',
          borderColor: 'divider',
          bgcolor: 'action.hover',
        },
        ...(Array.isArray(sx) ? sx : [sx]),
      ]}
      {...rest}
    />
  )
}

