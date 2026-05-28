import { useState, useEffect, useRef } from 'react';
import { api } from '../api';

const cache = new Map();

export default function useSchema(category, resourceType) {
  const [schema, setSchema] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const key = `${category}/${resourceType}`;

  useEffect(() => {
    if (!category || !resourceType) {
      setSchema(null);
      return;
    }

    if (cache.has(key)) {
      setSchema(cache.get(key));
      return;
    }

    let cancelled = false;
    setLoading(true);
    setError(null);

    api.getSchema(category, resourceType)
      .then((data) => {
        if (!cancelled) {
          cache.set(key, data);
          setSchema(data);
        }
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [key, category, resourceType]);

  return { schema, loading, error };
}

export function invalidateSchemaCache() {
  cache.clear();
}
