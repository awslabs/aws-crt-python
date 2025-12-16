"""
CRT Shape Base Class for CBOR Serialization

This module provides a base class for shape objects used by the CRT CBOR encoder.
Libraries like botocore can extend this base class directly, or use the provided implementations.
"""

from typing import Dict


class ShapeBase:
    """
    Base class for shape objects used by CRT CBOR encoding.

    This class defines the interface that shape implementations should follow.
    Libraries can extend this class directly to provide shape information
    to the CBOR encoder without requiring intermediate conversions.

    Subclasses must implement the type_name property and can override other
    properties as needed based on their shape type.
    """

    @property
    def type_name(self) -> str:
        """
        Return the shape type name.

        Returns:
            str: One of: 'structure', 'list', 'map', 'string', 'integer', 'long',
                 'float', 'double', 'boolean', 'blob', 'timestamp'

        Note:
            Subclasses must implement this property.
        """
        raise NotImplementedError("Subclasses must implement type_name property")

    @property
    def members(self) -> Dict[str, 'ShapeBase']:
        """
        For structure types, return dict of member name -> ShapeBase.

        Returns:
            Dict[str, ShapeBase]: Dictionary mapping member names to their shapes

        Raises:
            AttributeError: If called on non-structure type
        """
        raise AttributeError(f"Shape type {self.type_name} has no members")

    @property
    def member(self) -> 'ShapeBase':
        """
        For list types, return the ShapeBase of list elements.

        Returns:
            ShapeBase: Shape of list elements

        Raises:
            AttributeError: If called on non-list type
        """
        raise AttributeError(f"Shape type {self.type_name} has no member")

    @property
    def key(self) -> 'ShapeBase':
        """
        For map types, return the ShapeBase of map keys.

        Returns:
            ShapeBase: Shape of map keys

        Raises:
            AttributeError: If called on non-map type
        """
        raise AttributeError(f"Shape type {self.type_name} has no key")

    @property
    def value(self) -> 'ShapeBase':
        """
        For map types, return the ShapeBase of map values.

        Returns:
            ShapeBase: Shape of map values

        Raises:
            AttributeError: If called on non-map type
        """
        raise AttributeError(f"Shape type {self.type_name} has no value")

    def get_serialization_name(self, member_name: str) -> str:
        """
        Get the serialization name for a structure member.

        For structure types, returns the name to use in CBOR encoding.
        This allows for custom field name mappings (e.g., 'user_id' -> 'UserId').

        Args:
            member_name: The member name as it appears in the structure

        Returns:
            str: The name to use in CBOR encoding (may be same as member_name)

        Raises:
            AttributeError: If called on non-structure type
            ValueError: If member_name is not found in the structure
        """
        raise AttributeError(f"Shape type {self.type_name} has no serialization_name")
